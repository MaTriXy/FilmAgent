import os
import time
import uuid
import base64
import httpx
from openai import OpenAI
try:
    from tool.image_processor import ImageProcessor
except ImportError:
    from image_processor import ImageProcessor


class ImageGPT:
    """
    OpenAI 图片生成客户端
    支持模型：
        - sora_image → Images API
        - gpt-image-2 → Responses API
    """
    def __init__(self,
                 api_key: str = None,
                 base_url: str = None,
                 local_proxy: str = None,
                 timeout: float = 300.0):
        """
        OpenAI 图片生成客户端
        :param api_key: API Key
        :param base_url: 自定义 Base URL（如果传入，则不使用本地代理）
        :param timeout: 超时时间
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.timeout = timeout
        
        kwargs = {"api_key": self.api_key, "timeout": self.timeout}
        
        self.base_url = base_url
        if not self.base_url and local_proxy:
            kwargs["http_client"] = httpx.Client(
                proxy=local_proxy,
                timeout=self.timeout,
            )
        if self.base_url:
            kwargs["base_url"] = self.base_url
            
        self.client = OpenAI(**kwargs)
        self.max_attempts = 10
        self.image_processor = ImageProcessor()

    def generate_image(self, prompt, size="1024x1024", quality="standard", model=None,
                       save_dir=None, image_urls=None):
        """Generate a single image, download it, and return the local file path.

        Args:
            prompt: 图片描述提示词
            size: 图片尺寸
            quality: 图片质量
            model: 模型名称 (sora_image / gpt-image-2)
            save_dir: 保存目录（不传则返回 URL 或 base64）
            image_urls: 参考图片 URL 列表（仅 gpt-image-2 支持）
        """
        if model is None:
            model = "sora_image"

        print(f"Generating image with model '{model}'... Prompt: {prompt[:50]}...")

        # gpt-image-2 走官方 Responses API
        if model == "gpt-image-2":
            return self._generate_image_official(prompt, size=size, quality=quality,
                                                  save_dir=save_dir, image_urls=image_urls)

        # 其他模型走普通 Images API
        return self._generate_image_legacy(prompt, size=size, quality=quality,
                                            model=model, save_dir=save_dir)

    def _generate_image_official(self, prompt, size="1024x1024", quality="standard",
                                  save_dir=None, image_urls=None):
        """通过 Responses API 生成图片 (gpt-image-2)"""
        client = self.client

        # 构建 input content
        content = [{"type": "input_text", "text": prompt}]
        if image_urls:
            for url in image_urls:
                content.append({"type": "input_image", "image_url": url})

        attempts = 0
        last_error = None
        while attempts < self.max_attempts:
            try:
                response = client.responses.create(
                    model="gpt-image-2",
                    input=[{"role": "user", "content": content}],
                    tools=[{"type": "image_generation", "size": size, "quality": quality}],
                )

                # 从 output 中提取 image_generation_call 结果
                image_data = [
                    output.result for output in response.output
                    if output.type == "image_generation_call"
                ]

                if image_data:
                    b64 = image_data[0]
                    if save_dir:
                        os.makedirs(save_dir, exist_ok=True)
                        file_name = f"gptimg_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
                        file_path = os.path.join(save_dir, file_name)
                        with open(file_path, "wb") as f:
                            f.write(base64.b64decode(b64))
                        return file_path
                    else:
                        return b64  # 返回 base64 字符串
                else:
                    text_output = " ".join(
                        getattr(o, "text", "") for o in response.output if hasattr(o, "text")
                    ).strip()
                    print(f"gpt-image-2: 未返回图片。模型回复: {text_output[:200]}")
            except Exception as e:
                last_error = e
                print(f"gpt-image-2 Error: {e}. Retrying in 10s.")
            time.sleep(10)
            attempts += 1

        raise Exception(f"gpt-image-2: 达到最大重试次数。Last error: {last_error}")

    def _generate_image_legacy(self, prompt, size="1024x1024", quality="standard",
                                model="sora_image", save_dir=None):
        """通过 Images API 生成图片 (sora_image 等)"""
        # Fallback chain: user's choice -> sora_image
        models_to_try = [model, "sora_image"]
        models_to_try = list(dict.fromkeys(models_to_try))  # Remove duplicates

        attempts = 0
        last_error = None
        while attempts < self.max_attempts:
            for m in models_to_try:
                try:
                    response = self.client.images.generate(
                        model=m,
                        prompt=prompt,
                        size=size,
                        quality=quality,
                        n=1,
                    )
                    if response and response.data and response.data[0].url:
                        url = response.data[0].url
                        if save_dir:
                            os.makedirs(save_dir, exist_ok=True)
                            file_name = f"sora_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
                            file_path = os.path.join(save_dir, file_name)
                            if self.image_processor.download_image(url, file_path):
                                return file_path
                            else:
                                print(f"Failed to save image from {url}")
                        else:
                            return url
                except Exception as e:
                    last_error = e
                    msg = str(e)
                    # Model not found or no distributor: try next model
                    if "model_not_found" in msg or "无可用渠道" in msg or "distributor" in msg:
                        continue
                    # Other errors: wait before retry
                    print(f"Image generation error: {e}. Retrying in 10 seconds.")
                    time.sleep(10)
                    break  # Break inner loop to retry all models
            attempts += 1
        raise Exception(f"Max attempts reached, failed to generate image. Last error: {last_error}")

    def generate_images(self, prompt, count=4, size="1024x1024", quality="standard", model=None):
        """Generate multiple image URLs by calling Images API 'count' times."""
        urls = []
        for _ in range(count):
            url = self.generate_image(prompt=prompt, size=size, quality=quality, model=model)
            urls.append(url)
        return urls


if __name__ == "__main__":
    import sys
    import tempfile
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from config import Config

    print("=== GPT 图片生成可用性测试 ===")
    api_key = Config.OPENAI_API_KEY
    base_url = Config.OPENAI_BASE_URL

    if not api_key:
        print("✗ OPENAI_API_KEY 未设置，跳过")
        sys.exit(1)

    print(f"  API Key: {api_key[:6]}***")
    print(f"  Base URL: {base_url}")

    client = ImageGPT(api_key=api_key, base_url=Config.OPENAI_BASE_URL, local_proxy=Config.LOCAL_PROXY)

    # 1. sora_image 图片生成（仅尝试 1 次）
    img_prompt = "一只橘猫躺在阳光下的窗台上"
    print(f"\n[1/2] Prompt: {img_prompt}")
    client.max_attempts = 1
    t0 = time.time()
    save_dir = "result/image/test_avail"
    os.makedirs(save_dir, exist_ok=True)
    try:
        path = client.generate_image(prompt=img_prompt, size="1024x1024", model="sora_image", save_dir=save_dir)
        elapsed = time.time() - t0
        print(f"✓ 生成成功 ({elapsed:.1f}s): {path}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"✗ 图片生成失败 ({elapsed:.1f}s): {e}\n")

    # 2. gpt-image-2 图片生成
    img_prompt = "A cute orange cat lying on a sunny windowsill, watercolor style"
    print(f"\n[2/2] Prompt: {img_prompt}")
    client.max_attempts = 1
    t0 = time.time()
    save_dir = "result/image/test_avail"
    os.makedirs(save_dir, exist_ok=True)
    try:
        path = client.generate_image(prompt=img_prompt, size="1024x1024",
                                            model="gpt-image-2", save_dir=save_dir)
        elapsed = time.time() - t0
        print(f"✓ 生成成功 ({elapsed:.1f}s): {path}")
    except Exception as e:
        elapsed = time.time() - t0
        print(f"✗ gpt-image-2 失败 ({elapsed:.1f}s): {e}")
