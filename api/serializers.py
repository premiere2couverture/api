from rest_framework import serializers
from rest_framework.serializers import ModelSerializer
from .models import *
from .utils import est_majeur

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
    tags = serializers.SerializerMethodField()
    auteurs_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Auteur.objects.all(), source='auteurs'
    )
    tags_ids = serializers.PrimaryKeyRelatedField(
        many=True, write_only=True, queryset=Tag.objects.all(), source='tags'
    )

    class Meta:
        model = Livre
        fields = ['id', 'nom', 'date_sortie', 'nombre_pages', 'synopsis', 'edition', 'isbn', 'image', 'auteurs', 'tags', 'auteurs_ids', 'tags_ids']

    def get_tags(self, obj):
        """
        Filtre la liste des tags associés à ce livre en fonction de l'utilisateur qui fait la requête.
        """
        request = self.context.get('request')
        user = request.user if request else None
        
        tags = obj.tags.all()

        if not user or not user.is_authenticated or not est_majeur(user) or user.cacher_pour_adulte:
            tags = tags.filter(pour_adulte=False)

        return TagSerializer(tags, many=True).data

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
    
    def validate(self, data):
        """
        Validation personnalisée pour vérifier la cohérence des données.
        """
        date_debut = data.get('date_debut')
        date_fin = data.get('date_fin')

        if self.instance:
            date_debut = date_debut or self.instance.date_debut
            date_fin = date_fin or self.instance.date_fin

        if date_debut and date_fin and date_fin < date_debut:
            raise serializers.ValidationError({
                "date_fin": "La date de fin ne peut pas être antérieure à la date de début."
            })

        marque_pages = data.get('marque_pages')
        
        livre = data.get('livre')
        if not livre and self.instance:
            livre = self.instance.livre
            
        if marque_pages and livre and marque_pages > livre.nombre_pages:
             raise serializers.ValidationError({
                "marque_pages": f"Le marque-page ({marque_pages}) ne peut pas dépasser le nombre de pages du livre ({livre.nombre_pages})."
            })

        return data

