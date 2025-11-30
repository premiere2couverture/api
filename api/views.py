from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly, BasePermission
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404
from django.contrib.auth.models import Group
from .models import *
from .serializers import *
from .utils import est_majeur

class CustomLivrePermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method == 'POST':
            return request.user.has_perm('api.creer_livre')
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method in ['PUT', 'PATCH']:
            return request.user.has_perm('api.modifier_livre')
        if request.method == 'DELETE':
            return request.user.has_perm('api.suppression_livre')
        return False

class CustomAuteurPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method == 'POST':
            return request.user.has_perm('api.creer_auteur')
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method in ['PUT', 'PATCH']:
            return request.user.has_perm('api.modifier_auteur')
        if request.method == 'DELETE':
            return request.user.has_perm('api.supprimer_auteur')
        return False

class CustomTagPermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method == 'POST':
            return request.user.has_perm('api.creer_tag')
        return True

    def has_object_permission(self, request, view, obj):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True
        if request.method in ['PUT', 'PATCH']:
            return request.user.has_perm('api.modifier_tag')
        if request.method == 'DELETE':
            return request.user.has_perm('api.supprimer_tag')
        return False

class AuteurViewSet(ModelViewSet):
    queryset = Auteur.objects.all()
    serializer_class = AuteurSerializer
    permission_classes = [CustomAuteurPermission]

class TagViewSet(ModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = [CustomTagPermission]

    def perform_update(self, serializer):
        if not serializer.instance.modifiable:
            raise PermissionDenied("Ce tag ne peut être modifié.")
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.modifiable:
            raise PermissionDenied("Ce tag ne peut être supprimé.")
        instance.delete()

class UserViewSet(ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def wishlist(self, request):
        livres = request.user.liste_de_souhaits.all()
        serializer = LivreSerializer(livres, many=True)
        return Response(serializer.data)

class LivreViewSet(ModelViewSet):
    serializer_class = LivreSerializer
    permission_classes = [CustomLivrePermission]

    def get_queryset(self):
        user = self.request.user
        queryset = Livre.objects.prefetch_related('auteurs', 'tags')
        
        if user.is_authenticated and est_majeur(user) and not user.cacher_pour_adulte:
            return queryset
        else:
            return queryset.exclude(tags__pour_adulte=True)

    def get_object(self):
        obj = super().get_object()
        user = self.request.user
        if obj.tags.filter(pour_adulte=True).exists():
            if not user.is_authenticated or not est_majeur(user) or user.cacher_pour_adulte:
                raise PermissionDenied("Vous ne pouvez pas voir ce contenu.")
        return obj

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def add_to_wishlist(self, request, pk=None):
        livre = self.get_object()
        request.user.liste_de_souhaits.add(livre)
        return Response({'status': 'added to wishlist'})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated])
    def remove_from_wishlist(self, request, pk=None):
        livre = self.get_object()
        request.user.liste_de_souhaits.remove(livre)
        return Response({'status': 'removed from wishlist'})

class LectureViewSet(ModelViewSet):
    serializer_class = LectureSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Lecture.objects.filter(lecteur=self.request.user)

    def perform_create(self, serializer):
        livre = serializer.validated_data['livre']
        if Lecture.objects.filter(lecteur=self.request.user, livre=livre).exists():
             raise ValidationError("Vous avez déjà ce livre dans votre bibliothèque.")
        serializer.save(lecteur=self.request.user)

    def perform_update(self, serializer):
        if serializer.instance.lecteur != self.request.user:
            raise PermissionDenied("Cette lecture n'appartient pas à cet utilisateur.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.lecteur != self.request.user:
            raise PermissionDenied("Cette lecture n'appartient pas à cet utilisateur.")
        instance.delete()
