from django.urls import path, include
from .views import *
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

router = DefaultRouter()
router.register('auteurs', AuteurViewSet)
router.register('tags', TagViewSet, basename='tag')
router.register('users', UserViewSet)
router.register('livres', LivreViewSet, basename='livre')
router.register('lectures', LectureViewSet, basename='lecture')

urlpatterns = [
    path('', include(router.urls)),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]
