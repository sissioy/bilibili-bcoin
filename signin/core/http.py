"""
HTTP请求模块
提供同步和异步HTTP客户端，支持连接池和重试机制
"""
import json
import asyncio
import time
from typing import Dict, Optional, Any, Union
from contextlib import contextmanager
import httpx
from loguru import logger

from .exceptions import NetworkError


class SyncHttpClient:
    """
    同步HTTP客户端
    支持连接池、自动重试、超时控制
    """

    _instance: Optional['SyncHttpClient'] = None
    _client: Optional[httpx.Client] = None
    _max_get_attempts = 3

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, timeout: int = 30, max_connections: int = 100):
        self.timeout = timeout
        self.max_connections = max_connections

    @property
    def client(self) -> httpx.Client:
        """获取HTTP客户端实例（懒加载）"""
        if self._client is None:
            limits = httpx.Limits(max_connections=self.max_connections)
            self._client = httpx.Client(
                timeout=self.timeout,
                limits=limits,
                follow_redirects=True
            )
        return self._client

    def close(self) -> None:
        """关闭客户端"""
        if self._client:
            self._client.close()
            self._client = None

    @contextmanager
    def request_context(self):
        """请求上下文管理器"""
        try:
            yield self
        finally:
            pass

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """
        发送GET请求

        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
            cookies: Cookie

        Returns:
            响应对象
        """
        for attempt in range(self._max_get_attempts):
            try:
                response = self.client.get(
                    url,
                    params=params,
                    headers=headers,
                    cookies=cookies
                )
            except httpx.HTTPError as e:
                if attempt + 1 == self._max_get_attempts:
                    logger.error(f"GET请求失败: {url}, 错误: {e}")
                    raise NetworkError(f"GET请求失败: {e}", url=url) from e
                self._wait_before_retry(url, attempt, str(e))
                continue

            if not self._is_transient_status(response.status_code):
                return response
            if attempt + 1 == self._max_get_attempts:
                logger.error(f"GET请求失败: {url}, HTTP {response.status_code}")
                raise NetworkError(f"GET请求失败: HTTP {response.status_code}", url=url)
            self._wait_before_retry(url, attempt, f"HTTP {response.status_code}")

        raise NetworkError("GET请求失败", url=url)

    def _wait_before_retry(self, url: str, attempt: int, reason: str) -> None:
        delay = 2 ** attempt
        logger.warning(
            f"GET请求失败，{delay}秒后重试 "
            f"({attempt + 1}/{self._max_get_attempts - 1}): {url}, {reason}"
        )
        time.sleep(delay)

    def _is_transient_status(self, status_code: int) -> bool:
        return status_code in (408, 429) or status_code >= 500

    def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """
        发送POST请求

        Args:
            url: 请求URL
            data: 表单数据
            json_data: JSON数据
            headers: 请求头
            cookies: Cookie

        Returns:
            响应对象
        """
        try:
            response = self.client.post(
                url,
                data=data,
                json=json_data,
                headers=headers,
                cookies=cookies
            )
            return response
        except httpx.HTTPError as e:
            logger.error(f"POST请求失败: {url}, 错误: {e}")
            raise NetworkError(f"POST请求失败: {e}", url=url)

    def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送GET请求并返回JSON

        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
            cookies: Cookie

        Returns:
            JSON字典
        """
        response = self.get(url, params=params, headers=headers, cookies=cookies)
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {response.text[:200]}")
            return {}

    def post_json(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送POST请求并返回JSON

        Args:
            url: 请求URL
            data: 表单数据
            json_data: JSON数据
            headers: 请求头
            cookies: Cookie

        Returns:
            JSON字典
        """
        response = self.post(url, data=data, json_data=json_data, headers=headers, cookies=cookies)
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {response.text[:200]}")
            return {}


class AsyncHttpClient:
    """
    异步HTTP客户端
    支持连接池、自动重试、并发请求
    """

    _instance: Optional['AsyncHttpClient'] = None
    _client: Optional[httpx.AsyncClient] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, timeout: int = 30, max_connections: int = 100):
        self.timeout = timeout
        self.max_connections = max_connections

    @property
    def client(self) -> httpx.AsyncClient:
        """获取异步HTTP客户端实例（懒加载）"""
        if self._client is None:
            limits = httpx.Limits(max_connections=self.max_connections)
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                limits=limits,
                follow_redirects=True
            )
        return self._client

    async def close(self) -> None:
        """关闭客户端"""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """
        发送异步GET请求

        Args:
            url: 请求URL
            params: 查询参数
            headers: 请求头
            cookies: Cookie

        Returns:
            响应对象
        """
        try:
            response = await self.client.get(
                url,
                params=params,
                headers=headers,
                cookies=cookies
            )
            return response
        except httpx.HTTPError as e:
            logger.error(f"异步GET请求失败: {url}, 错误: {e}")
            raise NetworkError(f"异步GET请求失败: {e}", url=url)

    async def post(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """
        发送异步POST请求

        Args:
            url: 请求URL
            data: 表单数据
            json_data: JSON数据
            headers: 请求头
            cookies: Cookie

        Returns:
            响应对象
        """
        try:
            response = await self.client.post(
                url,
                data=data,
                json=json_data,
                headers=headers,
                cookies=cookies
            )
            return response
        except httpx.HTTPError as e:
            logger.error(f"异步POST请求失败: {url}, 错误: {e}")
            raise NetworkError(f"异步POST请求失败: {e}", url=url)

    async def get_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送异步GET请求并返回JSON
        """
        response = await self.get(url, params=params, headers=headers, cookies=cookies)
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {response.text[:200]}")
            return {}

    async def post_json(
        self,
        url: str,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        json_data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
        cookies: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """
        发送异步POST请求并返回JSON
        """
        response = await self.post(url, data=data, json_data=json_data, headers=headers, cookies=cookies)
        try:
            return response.json()
        except json.JSONDecodeError:
            logger.error(f"JSON解析失败: {response.text[:200]}")
            return {}

    async def batch_requests(
        self,
        requests: list,
        max_concurrent: int = 10
    ) -> list:
        """
        批量发送请求

        Args:
            requests: 请求列表，每个元素为 (method, url, kwargs) 元组
            max_concurrent: 最大并发数

        Returns:
            响应列表
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def limited_request(method: str, url: str, **kwargs):
            async with semaphore:
                if method.upper() == 'GET':
                    return await self.get(url, **kwargs)
                else:
                    return await self.post(url, **kwargs)

        tasks = [
            limited_request(method, url, **kwargs)
            for method, url, kwargs in requests
        ]

        return await asyncio.gather(*tasks, return_exceptions=True)


sync_http_client = SyncHttpClient()
async_http_client = AsyncHttpClient()
