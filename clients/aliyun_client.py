import json
import re
import socket
from typing import Any, Dict, List

from config import settings
from utils.logger import logger

try:
    from alibabacloud_ocr_api20210707.client import Client
    from alibabacloud_ocr_api20210707 import models as ocr_models
    from alibabacloud_tea_openapi.models import Config
    from alibabacloud_tea_util.models import RuntimeOptions

    ALIYUN_OCR_AVAILABLE = True
except ImportError:
    ALIYUN_OCR_AVAILABLE = False
    Client: Any = None
    ocr_models: Any = None
    Config: Any = None
    RuntimeOptions: Any = None
    logger.warning("阿里云OCR SDK不可用，将使用mock模式")


def _check_network(host: str, port: int = 443, timeout: int = 5) -> bool:
    """检查网络是否可达"""
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception:
        return False


class AliyunOCRClient:
    def __init__(self):
        self._network_available = True
        if ALIYUN_OCR_AVAILABLE:
            try:
                config = Config(
                    access_key_id=settings.ALIYUN_ACCESS_KEY_ID,
                    access_key_secret=settings.ALIYUN_ACCESS_KEY_SECRET,
                    endpoint=settings.ALIYUN_OCR_ENDPOINT,
                    region_id="cn-hangzhou",
                )
                self.client = Client(config)
                self.runtime = RuntimeOptions()
                
                # 检测网络
                host = settings.ALIYUN_OCR_ENDPOINT.replace("https://", "").replace("http://", "")
                if not _check_network(host):
                    logger.warning(f"无法连接到阿里云OCR服务: {host}，将使用mock模式")
                    self._network_available = False
                    
            except Exception as e:
                logger.error(f"初始化阿里云OCR客户端失败: {str(e)}")
                self.client = None
                self.runtime = None
                self._network_available = False
        else:
            self.client = None
            self.runtime = None
            self._network_available = False

    @property
    def _use_mock(self) -> bool:
        return (
            not ALIYUN_OCR_AVAILABLE
            or not self.client
            or not settings.is_aliyun_ocr_enabled
            or not self._network_available
        )

    def recognize_edu_paper_cut(self, image_path: str) -> List[Dict[str, Any]]:
        """调用阿里云试卷切题接口"""
        if self._use_mock:
            return self._mock_paper_cut(image_path)

        assert self.client is not None and self.runtime is not None
        client = self.client
        runtime = self.runtime
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            request = ocr_models.RecognizeEduPaperCutRequest(
                cut_type="question",
                image_type="photo",
                body=image_bytes,
            )
            response = client.recognize_edu_paper_cut_with_options(
                request, runtime
            )

            if not response or not response.body:
                logger.error("试卷切题API返回空响应")
                return self._mock_paper_cut(image_path)

            body = response.body
            
            body_dict = {}
            try:
                if hasattr(body, '__dict__'):
                    body_dict = vars(body)
                elif isinstance(body, dict):
                    body_dict = body
            except Exception as e:
                logger.error(f"获取响应体字典失败: {str(e)}")
            
            logger.debug(f"API响应体类型: {type(body)}")
            logger.debug(f"API响应体: {str(body)[:500]}")
            logger.debug(f"API响应体字典: {body_dict}")
            
            code = getattr(body, 'code', None)
            request_id = getattr(body, 'request_id', None) or getattr(body, 'RequestId', None)
            
            if code is not None and code != "OK":
                error_msg = getattr(body, 'message', '未知错误')
                if error_msg is None:
                    error_msg = str(body)
                logger.error(f"试卷切题API返回错误: {code}, 消息: {error_msg}, RequestId: {request_id}")
                return self._mock_paper_cut(image_path)

            data = getattr(body, 'data', None)
            
            if data is None:
                data = body_dict.get('Data', None)
            
            if data is None:
                logger.error(f"试卷切题API返回空数据, RequestId: {request_id}")
                return self._mock_paper_cut(image_path)

            logger.debug(f"响应数据类型: {type(data)}, 内容长度: {len(str(data)) if data else 0}")
            
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"解析响应JSON失败: {str(e)}")
                    return self._mock_paper_cut(image_path)
            
            questions = []
            
            if isinstance(data, dict):
                page_list = data.get('page_list', [])
                if isinstance(page_list, list):
                    page_index = 0
                    for page in page_list:
                        if isinstance(page, dict):
                            subject_list = page.get('subject_list', [])
                            if isinstance(subject_list, list) and subject_list:
                                for idx, subject in enumerate(subject_list, 1):
                                    if isinstance(subject, dict):
                                        x = subject.get('x', 0)
                                        y = subject.get('y', 0)
                                        width = subject.get('width', 0)
                                        height = subject.get('height', 0)
                                        
                                        if x == 0 and y == 0 and width == 0 and height == 0:
                                            content_list_info = subject.get('content_list_info', [])
                                            if isinstance(content_list_info, list) and content_list_info:
                                                content_info = content_list_info[0]
                                                if isinstance(content_info, dict):
                                                    pos = content_info.get('pos', [])
                                                    if isinstance(pos, list) and len(pos) >= 4:
                                                        x_coords = [p.get('x', 0) for p in pos if isinstance(p, dict)]
                                                        y_coords = [p.get('y', 0) for p in pos if isinstance(p, dict)]
                                                        if x_coords and y_coords:
                                                            x = min(x_coords)
                                                            y = min(y_coords)
                                                            width = max(x_coords) - x
                                                            height = max(y_coords) - y
                            
                                        text = subject.get('text', '')
                                        if not text:
                                            prism_words_info = subject.get('prism_wordsInfo', [])
                                            if isinstance(prism_words_info, list):
                                                words = [item.get('word', '') for item in prism_words_info if isinstance(item, dict)]
                                                if words:
                                                    text = ' '.join(words)
                            
                                        if x >= 0 and y >= 0 and width > 0 and height > 0:
                                            questions.append({
                                                "question_no": str(page_index * 100 + idx),
                                                "x1": int(x),
                                                "y1": int(y),
                                                "x2": int(x + width),
                                                "y2": int(y + height),
                                                "text": text.strip() if text else None,
                                            })
                        page_index += 1
            
            if not questions:
                logger.warning("API未识别到题目，使用模拟数据")
                questions = self._mock_paper_cut(image_path)

            logger.info("试卷切题完成，共识别到{}道题", len(questions))
            return questions

        except Exception as e:
            logger.error("试卷切题失败: {}", str(e), exc_info=True)
            if "getaddrinfo" in str(e) or "Max retries" in str(e) or "timeout" in str(e).lower():
                logger.warning("网络不可用，切换到mock模式")
                self._network_available = False
                return self._mock_paper_cut(image_path)
            logger.warning("OCR API调用失败，降级到mock模式")
            return self._mock_paper_cut(image_path)

    def recognize_edu_question_ocr(self, image_path: str) -> Dict[str, Any]:
        """调用阿里云题目OCR接口"""
        if self._use_mock:
            return self._mock_question_ocr(image_path)

        assert self.client is not None and self.runtime is not None
        client = self.client
        runtime = self.runtime
        try:
            with open(image_path, "rb") as f:
                image_bytes = f.read()

            request = ocr_models.RecognizeEduQuestionOcrRequest(
                need_rotate=True,
                body=image_bytes,
            )
            response = client.recognize_edu_question_ocr_with_options(
                request, runtime
            )

            if not response or not response.body:
                logger.error("题目OCR API返回空响应")
                return self._mock_question_ocr(image_path)

            body = response.body
            
            body_dict = {}
            try:
                if hasattr(body, '__dict__'):
                    body_dict = vars(body)
            except Exception:
                pass
            
            logger.debug(f"OCR API响应体: {body_dict}")
            
            code = getattr(body, 'code', None)
            if code is not None and code != "OK":
                error_msg = getattr(body, 'message', '未知错误')
                if error_msg is None:
                    error_msg = str(body)
                logger.error(f"题目OCR API返回错误: {code}, 消息: {error_msg}")
                return self._mock_question_ocr(image_path)

            data = getattr(body, 'data', None)
            
            if data is None:
                data = body_dict.get('Data', None)
            
            if data is None:
                logger.error("题目OCR API返回空数据")
                return self._mock_question_ocr(image_path)

            logger.debug(f"OCR响应数据类型: {type(data)}, 内容长度: {len(str(data)) if data else 0}")
            
            if isinstance(data, bytes):
                data = data.decode('utf-8')
            
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except json.JSONDecodeError as e:
                    logger.error(f"解析OCR响应JSON失败: {str(e)}")
                    return self._mock_question_ocr(image_path)
            
            if not isinstance(data, dict):
                logger.error("OCR响应数据格式错误")
                return self._mock_question_ocr(image_path)

            question_text = data.get("QuestionText", "") or data.get("text", "") or data.get("content", "")
            student_answer = data.get("AnswerText", "") or data.get("answer", "") or data.get("StudentAnswer", "")
            
            prism_words_info = data.get("prism_wordsInfo", [])
            if prism_words_info and isinstance(prism_words_info, list):
                words = [item.get("word", "") for item in prism_words_info if isinstance(item, dict)]
                if words:
                    text_from_words = " ".join(words)
                    if not question_text:
                        question_text = text_from_words

            if not question_text:
                question_text = self._extract_text_from_words(prism_words_info)

            if not student_answer:
                student_answer = self._extract_student_answer(data, question_text)

            question_type = data.get("QuestionType", "") or data.get("question_type", "")
            if not question_type:
                question_type = self._detect_question_type(question_text)
                logger.debug(f"自动推断题型: {question_type}")

            ocr_result = {
                "question_text": question_text.strip(),
                "student_answer": student_answer.strip(),
                "question_type": question_type,
                "raw_response": data,
            }

            logger.debug(f"题目OCR完成: {ocr_result['question_text'][:30]}...")
            return ocr_result

        except Exception as e:
            logger.opt(exception=True).error("题目OCR失败: {}", str(e))
            if "getaddrinfo" in str(e) or "Max retries" in str(e) or "timeout" in str(e).lower():
                logger.warning("网络不可用，切换到mock模式")
                self._network_available = False
                return self._mock_question_ocr(image_path)
            logger.warning("题目OCR API调用失败，降级到mock模式")
            return self._mock_question_ocr(image_path)

    def _extract_text_from_words(self, words_info: list) -> str:
        """从wordsInfo中提取文本"""
        if not isinstance(words_info, list):
            return ""
        
        words = []
        for item in words_info:
            if isinstance(item, dict):
                word = item.get("word", "")
                if word:
                    words.append(word)
            elif hasattr(item, 'word'):
                words.append(str(getattr(item, 'word', '')))
        
        return " ".join(words)

    def _extract_student_answer(self, data: dict, question_text: str) -> str:
        """从OCR结果中提取学生答案

        策略：
        1. 优先从 prism_wordsInfo 中提取 recClassify=2 的手写内容
        2. 若没有手写标记，从 content 中截取题干之后的部分
        """
        prism_info = data.get("prism_wordsInfo", [])
        if isinstance(prism_info, list):
            handwritten = [
                item.get("word", "").strip()
                for item in prism_info
                if isinstance(item, dict) and item.get("recClassify") == 2
            ]
            if handwritten:
                answer = " ".join(handwritten)
                logger.debug(f"提取手写答案: {answer[:30]}...")
                return answer

        # fallback: 从 content 截取题干之后的内容
        content = data.get("content", "") or data.get("text", "")
        if content and question_text and len(content) > len(question_text) + 5:
            idx = content.find(question_text)
            if idx >= 0:
                remaining = content[idx + len(question_text):].strip()
                if remaining and len(remaining) < 200:
                    return remaining

        return ""

    def _detect_question_type(self, content: str) -> str:
        """从题目内容自动推断题型"""
        if not content:
            return "解答题"
        text = content.strip()
        # 选择题：有编号选项 A. B. C. D.
        if re.search(r"[A-E][\.\、\s]", text) and re.search(r"[A-E]\.[^a-z]", text):
            return "选择题"
        # 判断题：含 对/错/正确/错误/√/×
        if re.search(r"(正确|错误|对[\.\s]|错[\.\s]|[√×✓✗])", text):
            return "判断题"
        # 填空题：有下划线或明显留空
        if re.search(r"[_＿]{2,}|\(\s*\)|（\s*）", text):
            return "填空题"
        # 计算/化简/求解题
        if re.search(r"(计算|化简|求[解值]|解方程|解不等式|求值|简化|展开)", text):
            return "计算题"
        # 口算题
        if re.search(r"(口算|直接写出得数|速算)", text):
            return "口算题"
        return "解答题"

    def _mock_paper_cut(self, image_path: str) -> List[Dict[str, Any]]:
        logger.info(f"使用mock模式进行试卷切题: {image_path}")
        
        try:
            import cv2
            img = cv2.imread(image_path)
            if img is not None:
                height, width = img.shape[:2]
                logger.debug(f"图片尺寸: {width}x{height}")
                
                margin = 20
                block_width = min(width - margin * 2, 400)
                block_height = min(int(height / 3) - margin, 150)
                
                if block_width > 50 and block_height > 50:
                    return [
                        {
                            "question_no": "1",
                            "x1": margin,
                            "y1": margin,
                            "x2": margin + block_width,
                            "y2": margin + block_height,
                        },
                        {
                            "question_no": "2",
                            "x1": margin,
                            "y1": margin * 2 + block_height,
                            "x2": margin + block_width,
                            "y2": margin * 2 + block_height * 2,
                        },
                        {
                            "question_no": "3",
                            "x1": margin,
                            "y1": margin * 3 + block_height * 2,
                            "x2": margin + block_width,
                            "y2": margin * 3 + block_height * 3,
                        },
                    ]
        except Exception as e:
            logger.error(f"读取图片尺寸失败: {str(e)}")
        
        return [
            {"question_no": "1", "x1": 10, "y1": 10, "x2": 100, "y2": 80},
            {"question_no": "2", "x1": 10, "y1": 100, "x2": 100, "y2": 170},
            {"question_no": "3", "x1": 10, "y1": 190, "x2": 100, "y2": 260},
        ]

    def _mock_question_ocr(self, image_path: str) -> Dict[str, Any]:
        logger.info(f"使用mock模式进行题目OCR: {image_path}")
        return {
            "question_text": "1. 下列二次根式中，是最简二次根式的有",
            "student_answer": "A",
            "question_type": "选择题",
            "raw_response": {},
        }


aliyun_ocr_client = AliyunOCRClient()