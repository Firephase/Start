from app.bot.handlers import router
from app.bot.middleware import AllowlistMiddleware

router.message.outer_middleware(AllowlistMiddleware())

__all__ = ["router"]
