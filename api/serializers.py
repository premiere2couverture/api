from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from .models import *

class AuteurSerializer(ModelSerializer):
    class Meta:
        model = Auteur
        fields = ['id', 'nom', 'date_naissance', 'date_mort', 'biographie']

class TagSerializer(ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'tag', 'pour_adulte', 'modifiable']

class UserSerializer(ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'username', 'password', 'email', 'first_name', 'last_name', 'date_naissance', 'cacher_pour_adulte']

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        user = super().update(instance, validated_data)
        
        if password:
            user.set_password(password)
            user.save()
            
        return user

class LivreSerializer(ModelSerializer):
    auteurs = AuteurSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)
    auteurs_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Auteur.objects.all(), source='auteurs'
    )
    tags_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Tag.objects.all(), source='tags'
    )

    class Meta:
        model = Livre
        fields = ['id', 'nom', 'date_sortie', 'nombre_pages', 'synopsis', 'edition', 'isbn', 'image', 'auteurs', 'tags', 'auteurs_ids', 'tags_ids']

class LectureSerializer(ModelSerializer):
    livre = LivreSerializer(read_only=True)
    livre_id = serializers.PrimaryKeyRelatedField(
        write_only=True, queryset=Livre.objects.all(), source='livre'
    )
    lecteur = UserSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = ['id', 'date_debut', 'date_fin', 'statut', 'note', 'marque_pages', 'commentaire', 'livre', 'livre_id', 'lecteur']
        read_only_fields = ['lecteur']

