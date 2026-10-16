import json
import re
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from typing import Optional
from config import settings
from utils.logger import logger


@dataclass
class GradeResult:
    question_block_id: int = 0
    question_no: str = ""
    score: float = 0
    max_score: float = 0
    result: str = "错误"
    comment: str = ""
    analysis: str = ""
    confidence: float = 0.0


try:
    import dashscope
    from dashscope import Generation

    DASHSCOPE_AVAILABLE = True
except ImportError:
    DASHSCOPE_AVAILABLE = False
    logger.warning("DashScope SDK不可用，将使用mock模式")

try:
    import pybreaker

    def on_failure_handler(exc):
        logger.error(f"大模型调用失败: {str(exc)}")

    circuit_breaker = pybreaker.CircuitBreaker(
        fail_max=5,
        reset_timeout=30,
    )
    circuit_breaker.on_failure = on_failure_handler
except ImportError:
    circuit_breaker = None
    logger.warning("pybreaker不可用，将不使用熔断器")

# Note: API key is set per-instance in __init__ via ModelConfig


class DeepSeekClient:
    def __init__(self, model_config=None):
        if model_config and model_config.api_key:
            self.api_key = model_config.api_key
            self.base_url = model_config.base_url
            self.model = model_config.model_id or model_config.name
            self.max_tokens = model_config.max_tokens
            self.temperature = model_config.temperature
        elif DASHSCOPE_AVAILABLE:
            tmodels = settings.text_models
            if tmodels:
                m = tmodels[0]
                self.api_key = m.api_key
                self.base_url = m.base_url
                self.model = m.model_id or m.name
                self.max_tokens = m.max_tokens
                self.temperature = m.temperature
            else:
                self.model = "mock"
        else:
            self.model = "mock"

    def grade_homework(self, ocr_results: list) -> list:
        """调用大模型进行作业批改（批量）"""
        if not DASHSCOPE_AVAILABLE:
            return self._mock_grade_homework(ocr_results)

        try:
            messages = self._build_prompt(ocr_results)

            if circuit_breaker:
                response = circuit_breaker.call(
                    self._call_dashscope,
                    messages=messages,
                )
            else:
                response = self._call_dashscope(messages=messages)

            results = self._parse_response(response)
            logger.info(f"大模型批改完成，共批改{len(results)}道题")
            return results

        except Exception as e:
            logger.error(f"大模型批改失败: {str(e)}", exc_info=True)
            raise

    def grade_question(
        self,
        question_type: str,
        question_text: str,
        student_answer: str,
        standard_answer: str,
        max_score: float,
    ) -> GradeResult:
        """单题智能批改"""
        if not DASHSCOPE_AVAILABLE:
            return self._mock_grade_question(
                question_type, question_text, student_answer, standard_answer, max_score
            )

        try:
            user_prompt = f"""
            你是一名严谨的中小学{question_type}学科教师，负责批改学生作业。请以严肃、准确的态度进行批改。

            输出格式必须是JSON，包含以下字段：
            - correct_answer: 正确答案及详细解题步骤
            - score: 学生得分（0到{max_score}之间的数字）
            - max_score: 满分
            - result: 批改结果（正确/错误/部分正确）
            - comment: 简洁评语
            - analysis: 详细分析（解题思路、错误原因、知识点）
            - knowledge_points: 涉及的知识点列表
            - tips: 针对性学习建议

            批改标准：
            1. 严格按照学科知识和教学大纲进行判断
            2. 解题步骤必须准确无误
            3. 评分标准要公正合理
            4. 分析要条理清晰，重点突出
            5. 语言要规范、准确、专业

            题目类型：{question_type}
            题目：{question_text}
            学生答案：{student_answer}
            满分：{max_score}
            """

            system_prompt = """
            你是一名专业的中小学教师，精通数学、语文、英语等学科知识。
            批改要求：
            - 解答过程严谨准确
            - 知识点标注精准
            - 评语客观公正
            - 分析条理清晰
            - 语言规范专业
            """

            messages = [
                {"role": "user", "content": system_prompt.strip() + "\n\n" + user_prompt.strip()},
            ]
            if circuit_breaker:
                response = circuit_breaker.call(self._call_dashscope, messages=messages)
            else:
                response = self._call_dashscope(messages=messages)

            result = self._parse_json_response(response)
            return GradeResult(
                question_block_id=0,
                question_no="",
                score=result.get("score", 0),
                max_score=result.get("max_score", max_score),
                result=result.get("result", "错误"),
                comment=result.get("comment", ""),
                analysis=result.get("analysis", ""),
                confidence=0.8,
            )

        except Exception as e:
            logger.error(f"单题批改失败，降级为mock: {str(e)}")
            return self._mock_grade_question(
                question_type, question_text, student_answer, standard_answer, max_score
            )

    def grade_question_directly(
        self,
        question_type: str,
        question_text: str,
        student_answer: str,
        max_score: float,
    ) -> GradeResult:
        """无标准答案时的直接批改：让 LLM 自己解题，然后对照学生答案评分"""
        if not DASHSCOPE_AVAILABLE or not settings.is_llm_enabled:
            logger.debug(
                f"LLM直接批改: SDK可用={DASHSCOPE_AVAILABLE}, LLM启用={settings.is_llm_enabled}, 使用mock"
            )
            return self._mock_grade_question(
                question_type, question_text, student_answer, "", max_score
            )

        try:
            user_prompt = f"""
            你是一名严谨的中小学教师。请按照以下步骤进行：
            1. 仔细阅读题目，独立推导正确答案
            2. 对照学生答案进行客观批改
            3. 给出准确的评分和详细分析

            输出格式：仅输出JSON对象，使用双引号，不含markdown代码块。
            JSON字段：
            - correct_answer: 正确答案及推导过程（详细步骤）
            - score: 得分（0到{max_score}的数字）
            - max_score: 满分（{max_score}）
            - result: 结论（正确/部分正确/错误）
            - comment: 简洁评语（专业、准确）
            - analysis: 详细分析（解题思路、错误分析、知识点）

            要求：
            - 解题过程要严谨准确
            - 评分要公正合理
            - 分析要条理清晰
            - 语言要规范专业

            题目类型：{question_type}
            题目：{question_text}
            学生答案：{student_answer}
            满分：{max_score}
            """

            messages = [
                {"role": "user", "content": user_prompt.strip()},
            ]

            if circuit_breaker:
                response = circuit_breaker.call(self._call_dashscope, messages=messages)
            else:
                response = self._call_dashscope(messages=messages)

            result = self._parse_json_response(response)
            return GradeResult(
                question_block_id=0,
                question_no="",
                score=result.get("score", 0),
                max_score=result.get("max_score", max_score),
                result=result.get("result", "错误"),
                comment=result.get("comment", ""),
                analysis=result.get("analysis", ""),
                confidence=0.75,
            )

        except Exception as e:
            logger.error(f"LLM直接批改失败，降级为mock: {str(e)}")
            return self._mock_grade_question(
                question_type, question_text, student_answer, "", max_score
            )

    def _call_dashscope(self, messages: list) -> str:
        """调用 LLM API：优先 DashScope 原生接口，失败后尝试 OpenAI 兼容接口"""
        response_text, error = self._try_dashscope(messages)
        if response_text is not None:
            return response_text

        logger.warning(f"DashScope 接口失败({error})，尝试 OpenAI 兼容接口...")
        response_text, error2 = self._try_openai_compatible(messages)
        if response_text is not None:
            logger.info("OpenAI 兼容接口调用成功")
            return response_text

        raise Exception(
            f"所有 API 接口均失败。DashScope: {error} | OpenAI兼容: {error2}"
        )

    def _try_dashscope(self, messages: list) -> tuple:
        """DashScope 原生接口"""
        try:
            if DASHSCOPE_AVAILABLE and hasattr(self, 'api_key'):
                dashscope.api_key = self.api_key
            response = Generation.call(
                model=getattr(self, 'model', 'qwen-turbo'),
                messages=messages,
                result_format="json",
                max_tokens=getattr(self, 'max_tokens', 2048),
                temperature=getattr(self, 'temperature', 0.1),
            )
            if response.status_code == 200:
                return response.output.choices[0].message.content, None
            error = f"status={response.status_code}, code={response.code}, msg={response.message}"
            logger.warning(f"DashScope: {error}")
            return None, error
        except Exception as e:
            return None, str(e)

    def _try_openai_compatible(self, messages: list) -> tuple:
        """OpenAI 兼容接口（支持 DeepSeek 直连、百炼兼容模式等）

        尝试顺序：
        1. 百炼 OpenAI 兼容端点 (使用 DashScope key)
        2. DeepSeek 官方 API (使用相同 key)
        """
        endpoints = [
            (
                "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                self.model,
            ),
            (
                "https://api.deepseek.com/v1/chat/completions",
                "deepseek-chat",
            ),
        ]

        last_error = None
        for url, model_name in endpoints:
            try:
                body = json.dumps(
                    {
                        "model": model_name,
                        "messages": messages,
                        "max_tokens": 2048,
                        "temperature": 0.1,
                        "response_format": {"type": "json_object"},
                    }
                ).encode("utf-8")

                req = urllib.request.Request(
                    url,
                    data=body,
                    headers={
                        "Authorization": f"Bearer {getattr(self, 'api_key', '')}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )

                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    logger.debug(f"OpenAI兼容接口成功: {url}")
                    return content, None

            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace")
                last_error = f"{url}: HTTP {e.code} - {error_body[:200]}"
                logger.warning(last_error)
            except Exception as e:
                last_error = f"{url}: {str(e)}"
                logger.warning(last_error)

        return None, last_error or "未知错误"

    def _build_prompt(self, ocr_results: list) -> list:
        """构建批改提示词"""
        questions_text = "\n".join(
            [
                f"题目{i+1}（{ocr.get('question_type', '未知')}）：\n问题：{ocr.get('question_text', '')}\n学生答案：{ocr.get('student_answer', '')}"
                for i, ocr in enumerate(ocr_results)
            ]
        )

        system_prompt = """
        你是一名严谨的中小学教师，负责批改学生作业。请以严肃、准确、专业的态度进行批改。
        输出格式：JSON数组，每个元素包含以下字段：
        - question_no: 题目编号
        - score: 得分（0到满分的数字）
        - max_score: 满分（默认10分）
        - result: 结果（正确/错误/部分正确）
        - comment: 简洁评语（专业、客观）
        - analysis: 详细分析（解题思路、错误原因）
        要求：解答严谨、评分公正、分析清晰、语言规范。
        """

        user_prompt = f"""
        {system_prompt.strip()}

        请认真批改以下作业：

        {questions_text}

        请给出准确的批改结果。
        """

        return [
            {"role": "user", "content": user_prompt.strip()},
        ]

    def _parse_response(self, response: str) -> list:
        """解析大模型批量响应"""
        try:
            text = response.strip()
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*\n?", "", text)
                text = re.sub(r"\n?```\s*$", "", text)
            result = json.loads(text)
            if isinstance(result, list):
                return [
                    GradeResult(
                        question_block_id=idx,
                        question_no=str(r.get("question_no", idx + 1)),
                        score=r.get("score", 0),
                        max_score=r.get("max_score", 10),
                        result=r.get("result", "错误"),
                        comment=r.get("comment", ""),
                        analysis=r.get("analysis", ""),
                        confidence=0.8,
                    )
                    for idx, r in enumerate(result)
                ]
            return []
        except json.JSONDecodeError:
            logger.error(f"解析大模型响应失败: {response}")
            return []

    def _mock_grade_homework(self, ocr_results: list) -> list:
        """Mock大模型批改结果（批量）"""
        logger.info(f"使用mock模式进行作业批改，共{len(ocr_results)}道题")
        results = []
        for idx, ocr in enumerate(ocr_results):
            question_type = ocr.get("question_type", "计算题")
            student_answer = ocr.get("student_answer", "").strip()

            if question_type == "计算题":
                if student_answer == "5" or student_answer == "五":
                    score = 10
                    result = "正确"
                    comment = "计算正确"
                else:
                    score = 0
                    result = "错误"
                    comment = "计算错误"
            elif question_type == "选择题":
                if student_answer.upper() in ["A", "B", "C", "D"]:
                    score = 10
                    result = "正确"
                    comment = "回答正确"
                else:
                    score = 0
                    result = "错误"
                    comment = "答案格式错误"
            else:
                score = 5
                result = "部分正确"
                comment = "需要人工复核"

            results.append(
                GradeResult(
                    question_block_id=idx,
                    question_no=str(idx + 1),
                    score=score,
                    max_score=10,
                    result=result,
                    comment=comment,
                    analysis="",
                    confidence=0.7,
                )
            )
        return results

    def _mock_grade_question(
        self,
        question_type: str,
        question_text: str,
        student_answer: str,
        standard_answer: str,
        max_score: float,
    ) -> GradeResult:
        """Mock单题批改"""
        student_answer = student_answer.strip()
        standard_answer = standard_answer.strip()

        # 无标准答案时按非空给部分分
        if not standard_answer:
            if student_answer:
                return GradeResult(
                    question_block_id=0,
                    question_no="",
                    score=max_score * 0.5,
                    max_score=max_score,
                    result="部分正确",
                    comment="无标准答案参考，已根据作答内容给予部分分，请人工复核",
                    analysis="建议补充标准答案后重新批改",
                    confidence=0.3,
                )
            else:
                return GradeResult(
                    question_block_id=0,
                    question_no="",
                    score=0,
                    max_score=max_score,
                    result="错误",
                    comment="学生未作答且无标准答案参考",
                    analysis="",
                    confidence=0.5,
                )

        if question_type in ["选择题", "判断题"]:
            if student_answer.upper() == standard_answer.upper():
                return GradeResult(
                    question_block_id=0,
                    question_no="",
                    score=max_score,
                    max_score=max_score,
                    result="正确",
                    comment="回答正确",
                    analysis="答案与标准答案一致",
                    confidence=1.0,
                )
            else:
                return GradeResult(
                    question_block_id=0,
                    question_no="",
                    score=0,
                    max_score=max_score,
                    result="错误",
                    comment=f"正确答案是{standard_answer}",
                    analysis="答案与标准答案不符",
                    confidence=1.0,
                )
        elif question_type in ["计算题", "口算题"]:
            try:
                student_val = float(re.sub(r"[^\d.\-]", "", student_answer))
                standard_val = float(re.sub(r"[^\d.\-]", "", standard_answer))
                if abs(student_val - standard_val) < 1e-9:
                    return GradeResult(
                        question_block_id=0,
                        question_no="",
                        score=max_score,
                        max_score=max_score,
                        result="正确",
                        comment="计算正确",
                        analysis="计算结果正确",
                        confidence=1.0,
                    )
                elif abs(student_val - standard_val) < max(
                    0.01, abs(standard_val) * 0.01
                ):
                    return GradeResult(
                        question_block_id=0,
                        question_no="",
                        score=max_score * 0.5,
                        max_score=max_score,
                        result="部分正确",
                        comment="计算结果近似正确",
                        analysis="计算结果接近标准答案",
                        confidence=0.9,
                    )
            except:
                pass
            return GradeResult(
                question_block_id=0,
                question_no="",
                score=0,
                max_score=max_score,
                result="错误",
                comment="计算错误",
                analysis="计算结果与标准答案不符",
                confidence=0.8,
            )
        else:
            if student_answer and standard_answer and student_answer == standard_answer:
                return GradeResult(
                    question_block_id=0,
                    question_no="",
                    score=max_score,
                    max_score=max_score,
                    result="正确",
                    comment="回答正确",
                    analysis="答案与标准答案一致",
                    confidence=0.7,
                )
            return GradeResult(
                question_block_id=0,
                question_no="",
                score=max_score * 0.5,
                max_score=max_score,
                result="部分正确",
                comment="需要人工复核",
                analysis="主观题需要人工复核",
                confidence=0.5,
            )

    def _parse_json_response(self, response: str) -> dict:
        """解析 LLM 返回的 JSON，处理常见格式问题"""
        text = response.strip()

        # 剥离 markdown 代码块
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*\n?", "", text)
            text = re.sub(r"\n?```\s*$", "", text)

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 提取第一个 JSON 对象
        match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL)
        if match:
            text = match.group(0)

        # 修复常见 LLM 输出问题
        text = self._fix_json_text(text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败，原始响应前200字符: {response[:200]}")
            raise

    @staticmethod
    def _fix_json_text(text: str) -> str:
        """修复 LLM 返回的 JSON 常见格式问题（单引号等）"""
        # 修复中文引号
        text = text.replace('“', '"').replace('”', '"')
        text = text.replace('‘', "'").replace('’', "'")
        # 尝试提取 {...} 对象
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            text = m.group(0)
        # 修复单引号 key/value
        text = re.sub(r"'([^']+)'\s*:", r'"\1":', text)
        text = re.sub(r":\s*'([^']*)'", r': "\1"', text)
        return text


deepseek_client = DeepSeekClient()
