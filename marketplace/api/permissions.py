from rest_framework import permissions


class IsDeveloper(permissions.BasePermission):
    """
    Custom permission to allow only developers to access write actions.
    Allows safe methods (GET, HEAD, OPTIONS) for all users.
    """
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            getattr(request.user, 'user_type', None) == 'developer'
        )


class IsAppDeveloperOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow only the developer of an application to edit/delete it.
    Allows safe methods (GET, HEAD, OPTIONS) for all users.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(obj, 'developer') and
            obj.developer.user == request.user
        )


class IsReviewerOrReadOnly(permissions.BasePermission):
    """
    Custom permission to allow only the reviewer of a review to edit/delete it.
    Allows safe methods (GET, HEAD, OPTIONS) for all users.
    """
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(obj, 'reviewer') and
            obj.reviewer == request.user
        )
