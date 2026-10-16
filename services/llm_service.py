from clients.deepseek_client import DeepSeekClient, GradeResult
from schemas.homework import GradingResult
from config import settings
from utils.logger import logger


def _to_schema(r: GradeResult) -> GradingResult:
    accuracy = None
    if r.max_score > 0:
        accuracy = round(r.score / r.max_score * 100, 1)
    
    analysis_str = r.analysis
    if isinstance(r.analysis, dict):
        import json
        analysis_str = json.dumps(r.analysis, ensure_ascii=False)
    
    return GradingResult(
        question_block_id=r.question_block_id,
        question_no=r.question_no,
        score=r.score,
        max_score=r.max_score,
        accuracy=accuracy,
        result=r.result,
        comment=r.comment or None,
        analysis=analysis_str or None,
        confidence=r.confidence or None,
    )


class LLMService:
    def __init__(self):
        self._clients = {}

    def _get_client(self, model_name: str = None) -> DeepSeekClient:
        if not model_name:
            return DeepSeekClient()
        if model_name not in self._clients:
            cfg = settings.get_model_by_name(model_name)
            self._clients[model_name] = DeepSeekClient(cfg)
        return self._clients[model_name]

    def grade_without_answer(
        self,
        question_type: str,
        question_text: str,
        student_answer: str,
        max_score: float = 10.0,
        model_name: str = None,
    ) -> GradingResult:
        """使用指定模型批改题目"""
        try:
            if not question_text:
                return GradingResult(
                    question_block_id=0, question_no="",
                    score=0, max_score=0, accuracy=0,
                    result="待复核", comment="题目识别失败",
                )

            if not settings.is_llm_enabled and not model_name:
                return GradingResult(
                    question_block_id=0, question_no="",
                    score=0, max_score=max_score, accuracy=0,
                    result="待复核", comment="大模型未配置",
                )

            logger.info(f"LLM批改: model={model_name or 'default'}, type={question_type}, q={question_text[:30]}...")
            client = self._get_client(model_name)
            result = client.grade_question_directly(
                question_type, question_text, student_answer, max_score
            )
            logger.info(f"结果: {result.score}/{max_score} {result.result}")
            return _to_schema(result)

        except Exception as e:
            logger.opt(exception=True).error("批改失败: {}", str(e))
            return GradingResult(
                question_block_id=0, question_no="",
                score=0, max_score=max_score, accuracy=0,
                result="错误", comment="批改失败，请人工复核",
            )


    def grade_with_answer(
        self,
        question_type: str,
        question_text: str,
        student_answer: str,
        standard_answer: str,
        max_score: float = 10.0,
        model_name: str = None,
    ) -> GradingResult:
        """有标准答案参考时批改：规则引擎精确判断 + LLM 补充评语"""
        try:
            if not question_text:
                return GradingResult(
                    question_block_id=0, question_no="",
                    score=0, max_score=0, accuracy=0,
                    result="待复核", comment="题目识别失败",
                )

            logger.info(
                f"LLM批改(有标答): model={model_name or 'default'}, "
                f"type={question_type}, std={standard_answer[:15]}..."
            )
            client = self._get_client(model_name)
            result = client.grade_question(
                question_type, question_text, student_answer,
                standard_answer, max_score,
            )
            logger.info(f"结果: {result.score}/{max_score} {result.result}")
            return _to_schema(result)

        except Exception as e:
            logger.opt(exception=True).error("批改失败: {}", str(e))
            return GradingResult(
                question_block_id=0, question_no="",
                score=0, max_score=max_score, accuracy=0,
                result="错误", comment="批改失败，请人工复核",
            )


llm_service = LLMService()
