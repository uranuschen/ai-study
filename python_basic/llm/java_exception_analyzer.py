import os
from enum import Enum
from typing import List

from dotenv import load_dotenv
from openai import (
    OpenAI,
    APITimeoutError,
    APIConnectionError,
    APIError,
)
from pydantic import BaseModel, ValidationError


load_dotenv()


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ErrorLocation(BaseModel):
    class_name: str
    method: str
    line: int


class ExceptionAnalysis(BaseModel):
    exception_type: str
    location: ErrorLocation
    root_cause: str
    solutions: List[str]
    risk_level: RiskLevel


class JavaExceptionAnalyzer:

    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
            timeout=30
        )

    def analyze(self, error_stack: str):

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {
                        "role": "system",
                        "content": """
你是Java异常分析助手。

请分析用户提供的Java异常栈。

只返回JSON，不要返回Markdown。

格式：
{
  "exception_type": "异常类型",
  "location": {
    "class_name": "类名",
    "method": "方法名",
    "line": 行号
  },
  "root_cause": "最可能的根本原因",
  "solutions": [
    "解决方案1",
    "解决方案2"
  ],
  "risk_level": "LOW/MEDIUM/HIGH"
}
"""
                    },
                    {
                        "role": "user",
                        "content": error_stack
                    }
                ],
                max_tokens=800,
                temperature=0
            )

            content = response.choices[0].message.content

            result = ExceptionAnalysis.model_validate_json(content)

            return result

        except APITimeoutError as e:
            print("请求超时：", e)
            return None

        except APIConnectionError as e:
            print("连接失败：", e)
            return None

        except ValidationError as e:
            print("返回JSON校验失败：", e)
            return None

        except APIError as e:
            print("API调用失败：", e)
            return None

        except Exception as e:
            print("未知异常：", e)
            return None