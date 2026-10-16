import os
import uuid
from PIL import Image, ImageEnhance
from config import settings
from utils.logger import logger


class ImageService:
    """图像处理服务

    原则：云 OCR API（阿里云 RecognizeEduPaperCut / RecognizeEduQuestionOcr）
    设计接收原始照片，过度预处理反而降低识别率。本服务只做必要的校正和轻度增强。
    """

    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    def crop_question_blocks(self, image_path: str, question_blocks: list) -> list:
        """裁剪题目区域

        Args:
            image_path: 原始图片路径
            question_blocks: 题目区域列表，每个元素包含 x1, y1, x2, y2 坐标

        Returns:
            裁剪后的题目图片路径列表
        """
        result = []
        try:
            img = Image.open(image_path)
            img_width, img_height = img.size

            for idx, block in enumerate(question_blocks, 1):
                try:
                    x1 = int(block.get('x1', block.get('x', 0)))
                    y1 = int(block.get('y1', block.get('y', 0)))
                    x2 = int(block.get('x2', x1 + block.get('width', 100)))
                    y2 = int(block.get('y2', y1 + block.get('height', 100)))

                    x1 = max(0, x1)
                    y1 = max(0, y1)
                    x2 = min(img_width, x2)
                    y2 = min(img_height, y2)

                    if x2 <= x1 or y2 <= y1:
                        logger.warning(f"无效的裁剪坐标: x1={x1}, y1={y1}, x2={x2}, y2={y2}")
                        continue

                    question_img = img.crop((x1, y1, x2, y2))

                    out_name = f"question_{uuid.uuid4().hex}.jpg"
                    out_path = os.path.join(self.upload_dir, out_name)
                    
                    question_img = question_img.convert('RGB')
                    question_img.save(out_path, 'JPEG', quality=95)

                    result.append({
                        'id': str(uuid.uuid4()),
                        'question_no': str(block.get('question_no', idx)),
                        'image_path': out_path,
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                    })
                    logger.debug(f"成功裁剪题目图片: {out_path}")

                except Exception as e:
                    logger.error(f"裁剪题目 #{idx} 失败: {str(e)}")
                    continue

            if not result:
                logger.warning("未成功裁剪任何题目图片")

        except Exception as e:
            logger.error(f"裁剪题目区域失败: {str(e)}", exc_info=True)

        return result

    def enhance_for_ocr(self, image_path: str) -> str:
        """轻度增强图像用于OCR识别"""
        try:
            img = Image.open(image_path)
            
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)

            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.1)

            out_name = f"ocr_enhanced_{uuid.uuid4().hex}.png"
            out_path = os.path.join(self.upload_dir, out_name)
            img.save(out_path, 'PNG')
            
            return out_path
        except Exception as e:
            logger.warning(f"图像增强失败，使用原图: {str(e)}")
            return image_path


image_service = ImageService()
