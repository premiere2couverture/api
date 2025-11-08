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
    class Meta:
        model = User
        fields = ['id', 'username']

class LivreSerializer(ModelSerializer):
    auteurs = AuteurSerializer(many=True, read_only=True)
    tags = TagSerializer(many=True, read_only=True)

    class Meta:
        model = Livre
        fields = ['id', 'nom', 'date_sortie', 'nombre_pages', 'synopsis', 'edition', 'isbn', 'image', 'auteurs', 'tags']

class LectureSerializer(ModelSerializer):
    livre = LivreSerializer(read_only=True)
    lecteur = UserSerializer(read_only=True)

    class Meta:
        model = Lecture
        fields = ['id', 'date_debut', 'date_fin', 'statut', 'note', 'marque_pages', 'commentaire', 'livre', 'lecteur']
