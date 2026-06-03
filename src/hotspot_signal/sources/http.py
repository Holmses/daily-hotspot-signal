from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import ssl


@dataclass(slots=True)
class HttpResponse:
    url: str
    text: str
    status: int


class HttpClient:
    def __init__(
        self,
        user_agent: str | None = None,
        timeout_seconds: float = 12.0,
        verify_ssl: bool = True,
    ) -> None:
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 hotspot-signal/0.1"
        )
        self.timeout_seconds = timeout_seconds
        self.verify_ssl = verify_ssl

    def get_text(self, url: str) -> HttpResponse:
        request = Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/xml,application/json,text/plain;q=0.9,*/*;q=0.8",
            },
        )
        try:
            context = None if self.verify_ssl else ssl._create_unverified_context()
            with urlopen(request, timeout=self.timeout_seconds, context=context) as response:
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
                return HttpResponse(
                    url=response.geturl(),
                    text=body.decode(encoding, errors="replace"),
                    status=int(getattr(response, "status", 200)),
                )
        except HTTPError as error:
            raise RuntimeError(f"HTTP {error.code} for {url}") from error
        except URLError as error:
            raise RuntimeError(f"Failed to fetch {url}: {error.reason}") from error
