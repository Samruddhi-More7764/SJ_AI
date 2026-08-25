"""No login. Agent still needs a User object; this always returns the same one."""

from vanna.core.user import RequestContext, User, UserResolver


class NoAuthUserResolver(UserResolver):
    async def resolve_user(self, request_context: RequestContext) -> User:
        return User(id="local", username="stockjarvis", group_memberships=["user"])
