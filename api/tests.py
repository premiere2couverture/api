from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model
from .models import Livre, Lecture, Tag, Auteur
from datetime import date, timedelta
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
import shutil
import tempfile
import io
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
import os

User = get_user_model()

class SecurityTests(APITestCase):
    def setUp(self):
        # 1. Création de deux utilisateurs : Alice (Moi) et Bob (L'intrus)
        self.alice = User.objects.create_user(username='alice', password='password123', date_naissance='2000-01-01')
        self.bob = User.objects.create_user(username='bob', password='password123', date_naissance='2000-01-01')
        
        # 2. Création d'un livre
        self.livre = Livre.objects.create(
            nom="Test Book", date_sortie="2020-01-01", nombre_pages=100, synopsis="Test"
        )

        # 3. URLs
        self.token_url = reverse('token_obtain_pair')
        self.lecture_list_url = reverse('lecture-list')

    def get_token_for(self, user):
        """Helper pour récupérer le token JWT d'un user"""
        response = self.client.post(self.token_url, {
            'username': user.username,
            'password': 'password123'
        })
        return response.data['access']

    def test_lecture_is_private(self):
        """
        Test CRITIQUE : Bob ne doit pas voir les lectures d'Alice.
        """
        # Alice crée une lecture
        Lecture.objects.create(lecteur=self.alice, livre=self.livre, statut='a lire')

        # Bob se connecte
        token_bob = self.get_token_for(self.bob)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token_bob)

        # Bob demande la liste des lectures
        response = self.client.get(self.lecture_list_url)

        # Vérification
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0) # Bob ne doit rien voir !
        print("\n✅ Sécurité validée : Bob ne voit pas les lectures d'Alice.")

    def test_user_modification_permission(self):
        """
        Test CRITIQUE : Bob ne doit pas pouvoir modifier le profil d'Alice.
        """
        # Bob se connecte
        token_bob = self.get_token_for(self.bob)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token_bob)

        # Bob essaie de changer l'email d'Alice via l'API
        url_alice = reverse('user-detail', args=[self.alice.id])
        data = {'email': 'hacked@bob.com'}
        
        response = self.client.patch(url_alice, data)

        # Vérification : Doit être interdit (403)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        
        # On vérifie en base que l'email n'a pas changé
        self.alice.refresh_from_db()
        self.assertNotEqual(self.alice.email, 'hacked@bob.com')
        print("✅ Sécurité validée : Bob n'a pas pu modifier Alice.")

    def test_create_lecture_assigns_correct_user(self):
        """
        Vérifie que même si j'essaie de tricher en envoyant l'ID d'un autre,
        l'API force l'utilisateur connecté.
        """
        token_alice = self.get_token_for(self.alice)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token_alice)

        data = {
            'livre_id': self.livre.id,
            'statut': 'a lire',
            'lecteur': self.bob.id
        }

        response = self.client.post(self.lecture_list_url, data)

        if response.status_code != status.HTTP_201_CREATED:
            print("\nERREUR API:", response.data)

        # 1. On vérifie d'abord que la création a réussi (Code 201)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        
        # 2. Vérification : La lecture a été créée pour Alice, pas Bob
        lecture = Lecture.objects.latest('id')
        self.assertEqual(lecture.lecteur, self.alice) 
        print("✅ Intégrité validée : Le système a ignoré la tentative d'usurpation.")

class AdultContentTests(APITestCase):
    def setUp(self):
        # 1. Création des Tags
        self.tag_adulte = Tag.objects.create(tag="Horreur", pour_adulte=True, modifiable=True)
        self.tag_enfant = Tag.objects.create(tag="Jeunesse", pour_adulte=False, modifiable=True)

        # 2. Création des Livres
        # Livre A : Contenu Adulte
        self.livre_adulte = Livre.objects.create(
            nom="Livre Interdit", 
            date_sortie="2020-01-01", 
            nombre_pages=100, 
            synopsis="Contenu choquant"
        )
        self.livre_adulte.tags.add(self.tag_adulte)

        # Livre B : Contenu Tout Public
        self.livre_enfant = Livre.objects.create(
            nom="Livre Gentil", 
            date_sortie="2020-01-01", 
            nombre_pages=20, 
            synopsis="Histoire mignonne"
        )
        self.livre_enfant.tags.add(self.tag_enfant)

        # 3. Création des Utilisateurs (Calcul des âges)
        today = date.today()
        date_majeur = today - timedelta(days=365*20) # 20 ans
        date_mineur = today - timedelta(days=365*15) # 15 ans

        # Utilisateur Mineur (15 ans)
        self.mineur = User.objects.create_user(
            username='kid', password='password', date_naissance=date_mineur
        )

        # Adulte "Prude" (20 ans, mais veut cacher le contenu adulte)
        self.adulte_cache = User.objects.create_user(
            username='prude', password='password', date_naissance=date_majeur, 
            cacher_pour_adulte=True 
        )

        # Adulte "Open" (20 ans, veut voir le contenu adulte)
        self.adulte_visible = User.objects.create_user(
            username='open', password='password', date_naissance=date_majeur, 
            cacher_pour_adulte=False
        )

        self.list_url = reverse('livre-list') # basename='livre'

    def get_token_for(self, user):
        url = reverse('token_obtain_pair')
        resp = self.client.post(url, {'username': user.username, 'password': 'password'})
        return resp.data['access']

    def test_anonymous_sees_only_safe_content(self):
        """Un utilisateur non connecté ne voit PAS les livres adultes"""
        response = self.client.get(self.list_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [l['id'] for l in response.data]
        self.assertIn(self.livre_enfant.id, ids)
        self.assertNotIn(self.livre_adulte.id, ids)

    def test_minor_sees_only_safe_content(self):
        """Un mineur connecté ne voit PAS les livres adultes"""
        token = self.get_token_for(self.mineur)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        
        response = self.client.get(self.list_url)
        
        ids = [l['id'] for l in response.data]
        self.assertIn(self.livre_enfant.id, ids)
        self.assertNotIn(self.livre_adulte.id, ids)

    def test_adult_hidden_pref_sees_only_safe_content(self):
        """Un majeur qui a coché 'cacher_pour_adulte' ne voit PAS les livres adultes"""
        token = self.get_token_for(self.adulte_cache)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        
        response = self.client.get(self.list_url)
        
        ids = [l['id'] for l in response.data]
        self.assertIn(self.livre_enfant.id, ids)
        self.assertNotIn(self.livre_adulte.id, ids)

    def test_adult_visible_pref_sees_everything(self):
        """Un majeur qui veut voir le contenu adulte voit TOUT"""
        token = self.get_token_for(self.adulte_visible)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        
        response = self.client.get(self.list_url)
        
        ids = [l['id'] for l in response.data]
        self.assertIn(self.livre_enfant.id, ids)
        self.assertIn(self.livre_adulte.id, ids)

    def test_direct_access_restriction(self):
        """Test de sécurité : Essayer d'accéder directement à l'URL d'un livre adulte"""
        url_detail = reverse('livre-detail', args=[self.livre_adulte.id])
        
        # 1. Test Mineur -> Doit être interdit (403)
        token = self.get_token_for(self.mineur)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        resp = self.client.get(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # 2. Test Adulte Visible -> Doit être autorisé (200)
        token = self.get_token_for(self.adulte_visible)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        resp = self.client.get(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
    
    def test_serializer_logic_isolation(self):
        """
        Test unitaire : Vérifie DIRECTEMENT la logique du Serializer,
        en contournant la sécurité de la View.
        Cela confirme que SI un livre est affiché, ses tags sensibles sont masqués.
        """
        # 1. On prépare le livre avec un tag "Gentil" et un tag "Adulte"
        self.livre_enfant.tags.add(self.tag_adulte)
        
        # 2. On simule une requête faite par le mineur
        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        
        factory = APIRequestFactory()
        request = factory.get('/') # L'URL importe peu ici
        request.user = self.mineur # On force l'utilisateur mineur
        
        # 3. On instancie le sérialiseur avec ce contexte
        # C'est ce que fait la Vue en temps normal
        from .serializers import LivreSerializer
        serializer = LivreSerializer(
            self.livre_enfant, 
            context={'request': request}
        )
        
        # 4. On inspecte les données générées (le JSON)
        data = serializer.data
        tags_noms = [t['tag'] for t in data['tags']]
        
        # VÉRIFICATION
        # Le tag "Jeunesse" doit être là
        self.assertIn(self.tag_enfant.tag, tags_noms)
        # Le tag "Horreur" doit avoir disparu
        self.assertNotIn(self.tag_adulte.tag, tags_noms)

class PermissionTests(APITestCase):
    def setUp(self):
        # 1. Création d'un utilisateur "Lambda" (sans aucune permission spéciale)
        self.user_lambda = User.objects.create_user(
            username='lambda', 
            password='password123', 
            date_naissance='1990-01-01' # Majeur pour éviter le filtre 404 des livres
        )

        # 2. Création de données existantes pour tenter de les modifier
        self.auteur = Auteur.objects.create(nom="Victor Hugo")
        self.tag = Tag.objects.create(tag="Classique", pour_adulte=False)
        self.livre = Livre.objects.create(
            nom="Les Misérables", 
            date_sortie="1862-01-01", 
            nombre_pages=1500, 
            synopsis="Jean Valjean..."
        )

    def get_token_for(self, user):
        url = reverse('token_obtain_pair')
        resp = self.client.post(url, {'username': user.username, 'password': 'password123'})
        return resp.data['access']

    def test_auteur_permissions(self):
        """Test: Un utilisateur lambda ne peut pas créer/modifier/supprimer d'auteur"""
        token = self.get_token_for(self.user_lambda)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. TENTATIVE DE CRÉATION (POST)
        url_list = reverse('auteur-list')
        resp = self.client.post(url_list, {'nom': 'Nouvel Auteur'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. TENTATIVE DE MODIFICATION (PUT/PATCH)
        url_detail = reverse('auteur-detail', args=[self.auteur.id])
        resp = self.client.put(url_detail, {'nom': 'Victor Hugo Modifié'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 3. TENTATIVE DE SUPPRESSION (DELETE)
        resp = self.client.delete(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 4. VERIFICATION LECTURE (GET) -> Doit être autorisé
        resp = self.client.get(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_tag_permissions(self):
        """Test: Un utilisateur lambda ne peut pas gérer les tags"""
        token = self.get_token_for(self.user_lambda)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. CRÉATION
        url_list = reverse('tag-list')
        resp = self.client.post(url_list, {'tag': 'Nouveau Tag', 'pour_adulte': False})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. MODIFICATION
        url_detail = reverse('tag-detail', args=[self.tag.id])
        resp = self.client.patch(url_detail, {'tag': 'Tag Modifié'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 3. SUPPRESSION
        resp = self.client.delete(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_livre_permissions(self):
        """Test: Un utilisateur lambda ne peut pas gérer les livres"""
        token = self.get_token_for(self.user_lambda)
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. CRÉATION
        url_list = reverse('livre-list') # basename='livre'
        data = {
            'nom': 'Mon Livre Pirate', 
            'date_sortie': '2023-01-01', 
            'nombre_pages': 100, 
            'synopsis': 'Test'
        }
        resp = self.client.post(url_list, data)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 2. MODIFICATION
        url_detail = reverse('livre-detail', args=[self.livre.id])
        resp = self.client.patch(url_detail, {'nom': 'Titre Hacké'})
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 3. SUPPRESSION
        resp = self.client.delete(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # 4. VERIFICATION LECTURE -> Autorisé
        resp = self.client.get(url_detail)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

class LogicConsistencyTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password', date_naissance='2000-01-01')
        self.livre = Livre.objects.create(
            nom="Livre Test", 
            date_sortie="2020-01-01", 
            nombre_pages=100,
            synopsis="Test"
        )
        self.url = reverse('lecture-list')

    def get_token(self):
        resp = self.client.post(reverse('token_obtain_pair'), {
            'username': 'testuser', 'password': 'password'
        })
        return resp.data['access']

    def test_date_coherence(self):
        """
        Vérifie qu'on ne peut pas mettre une date de fin avant la date de début.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        data = {
            'livre_id': self.livre.id,
            'statut': 'lu',
            'date_debut': '2023-12-31',
            'date_fin': '2023-01-01' # <--- Impossible logiquement
        }

        response = self.client.post(self.url, data)
        
        # On attend une erreur 400 Bad Request
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        # On vérifie que l'erreur mentionne bien les dates (non_field_errors ou champ spécifique)
        self.assertTrue('date_fin' in str(response.data) or 'non_field_errors' in str(response.data))

    def test_page_number_impossible(self):
        """
        Vérifie qu'on ne peut pas être à la page 150 d'un livre de 100 pages.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        data = {
            'livre_id': self.livre.id,
            'statut': 'en cours',
            'marque_pages': 150 # <--- Le livre ne fait que 100 pages
        }

        response = self.client.post(self.url, data)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_note_range(self):
        """
        Vérifie que la note doit être entre 1 et 5 (déjà géré par DRF choices, mais bon à tester).
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # Test note trop haute
        response = self.client.post(self.url, {
            'livre_id': self.livre.id, 'statut': 'lu', 'note': 6
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test note trop basse (0)
        response = self.client.post(self.url, {
            'livre_id': self.livre.id, 'statut': 'lu', 'note': 0
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_automatic_statut_logic(self):
        """
        Vérifie que si on envoie statut='lu', le marque-page se remplit tout seul 
        (grâce à votre méthode save() dans models.py).
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        data = {
            'livre_id': self.livre.id,
            'statut': 'lu',
            # On n'envoie PAS de marque_pages, ou on envoie 0
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # On recharge l'objet depuis la BDD pour vérifier le save()
        lecture_id = response.data['id']
        lecture = Lecture.objects.get(pk=lecture_id)

        # Votre logique métier doit avoir mis 100 (le max du livre)
        self.assertEqual(lecture.marque_pages, 100)

class DatabaseIntegrityTests(APITestCase):
    def setUp(self):
        # 1. Création de l'utilisateur
        self.user = User.objects.create_user(
            username='tester', 
            password='password123',
            date_naissance='2000-01-01' 
        )

        # 2. On donne la permission "creer_livre" à cet utilisateur pour qu'il puisse tester la création de doublons ISBN
        content_type = ContentType.objects.get_for_model(Livre)
        permission = Permission.objects.get(codename='creer_livre', content_type=content_type)
        self.user.user_permissions.add(permission)

        # 3. Un livre de base pour tester les lectures
        self.livre = Livre.objects.create(
            nom="Livre Unique", 
            date_sortie="2020-01-01", 
            nombre_pages=200, 
            synopsis="Test",
            isbn="978-0-00-000000-1" # ISBN initial
        )

    def get_token(self):
        url = reverse('token_obtain_pair')
        resp = self.client.post(url, {'username': 'tester', 'password': 'password123'})
        return resp.data['access']

    def test_duplicate_lecture_prevention(self):
        """
        Vérifie qu'on ne peut pas créer deux fiches de lecture 
        pour le même livre et le même utilisateur.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        url = reverse('lecture-list')

        data = {
            'livre_id': self.livre.id,
            'statut': 'a lire'
        }

        # 1. Première création : DOIT RÉUSSIR (201)
        response1 = self.client.post(url, data)
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # 2. Seconde création identique : DOIT ÉCHOUER (400)
        response2 = self.client.post(url, data)
        
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("déjà ce livre", str(response2.data))

    def test_isbn_cleaning(self):
        """
        Vérifie que si l'utilisateur envoie un ISBN avec des tirets,
        l'API le nettoie et le sauvegarde sans tirets.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        url = reverse('livre-list')

        # 1. On envoie un ISBN avec des tirets (Format UX)
        isbn_input = "978-2-1234-5678-9"
        isbn_expected = "9782123456789"

        data = {
            'nom': 'Livre Nettoyé',
            'date_sortie': '2023-01-01',
            'nombre_pages': 100,
            'synopsis': 'Test',
            'isbn': isbn_input, # <--- AVEC TIRETS
            'auteurs_ids': [],
            'tags_ids': []
        }

        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # 2. Vérification en base de données
        # On recharge le livre créé
        livre = Livre.objects.get(nom='Livre Nettoyé')
        
        # Le livre en base doit avoir l'ISBN "propre" (sans tirets)
        self.assertEqual(livre.isbn, isbn_expected)
        self.assertNotEqual(livre.isbn, isbn_input)

    def test_duplicate_isbn_prevention(self):
        """
        Vérifie qu'on ne peut pas créer deux livres différents avec le même ISBN,
        MÊME SI l'un est envoyé avec des tirets et l'autre sans.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)
        url = reverse('livre-list')

        # On définit le même ISBN sous deux formes
        isbn_avec_tirets = "978-0-1234-5678-9"
        isbn_sans_tirets = "9780123456789"

        # Livre A (Créé avec tirets)
        data1 = {
            'nom': 'Tome 1', 'date_sortie': '2023-01-01', 'nombre_pages': 100, 
            'synopsis': 'Synopsis 1',
            'isbn': isbn_avec_tirets, # <--- Format 1
            'auteurs_ids': [], 'tags_ids': []
        }

        # Livre B (Créé sans tirets)
        data2 = {
            'nom': 'Tome 2', 'date_sortie': '2023-02-01', 'nombre_pages': 150, 
            'synopsis': 'Synopsis 2',
            'isbn': isbn_sans_tirets, # <--- Format 2
            'auteurs_ids': [], 'tags_ids': []
        }

        # 1. Création du premier (Doit réussir et être nettoyé)
        response1 = self.client.post(url, data1)
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # 2. Création du second (Doit échouer car doublon détecté après nettoyage)
        response2 = self.client.post(url, data2)
        
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('isbn', response2.data)

class WishlistTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='fan_lecture', 
            password='password123',
            date_naissance='2000-01-01'
        )
        
        self.livre = Livre.objects.create(
            nom="Livre à souhaiter", 
            date_sortie="2022-01-01", 
            nombre_pages=300, 
            synopsis="Un super livre",
            isbn="9782000000000"
        )

        # 3. Préparation des URLs
        self.url_add = reverse('livre-add-to-wishlist', args=[self.livre.id])
        self.url_remove = reverse('livre-remove-from-wishlist', args=[self.livre.id])

    def get_token(self):
        resp = self.client.post(reverse('token_obtain_pair'), {
            'username': 'fan_lecture', 'password': 'password123'
        })
        return resp.data['access']

    def test_wishlist_add_and_remove(self):
        """
        Vérifie le cycle de vie normal : Ajout puis Retrait.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. AJOUT
        response = self.client.post(self.url_add)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        # Vérification en base
        self.assertTrue(self.user.liste_de_souhaits.filter(id=self.livre.id).exists())
        self.assertEqual(self.user.liste_de_souhaits.count(), 1)

        # 2. RETRAIT
        response = self.client.post(self.url_remove)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Vérification en base
        self.assertFalse(self.user.liste_de_souhaits.filter(id=self.livre.id).exists())
        self.assertEqual(self.user.liste_de_souhaits.count(), 0)

    def test_wishlist_duplicate_add(self):
        """
        Vérifie que l'ajout multiple du même livre ne plante pas
        et ne crée pas de doublons (Many-to-Many gère ça nativement).
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # Premier ajout
        self.client.post(self.url_add)
        
        # Second ajout (tentative de doublon)
        response = self.client.post(self.url_add)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.liste_de_souhaits.count(), 1)

    def test_wishlist_remove_non_existent(self):
        """
        Vérifie que retirer un livre qui n'est pas dans la liste
        ne provoque pas d'erreur.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # On s'assure que la liste est vide au départ
        self.assertEqual(self.user.liste_de_souhaits.count(), 0)

        # Tentative de retrait d'un livre qui n'y est pas
        response = self.client.post(self.url_remove)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.liste_de_souhaits.count(), 0)

MEDIA_ROOT_TEST = tempfile.mkdtemp()

@override_settings(MEDIA_ROOT=MEDIA_ROOT_TEST)
class ImageLifecycleTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        # Nettoyage : On supprime le dossier temporaire à la fin des tests
        shutil.rmtree(MEDIA_ROOT_TEST, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        # 1. Création d'un utilisateur "Bibliothécaire" avec les droits
        self.user = User.objects.create_user(
            username='librarian', 
            password='password123',
            date_naissance='1980-01-01'
        )
        # On lui donne tous les droits sur les livres
        content_type = ContentType.objects.get_for_model(Livre)
        perms = Permission.objects.filter(content_type=content_type)
        self.user.user_permissions.set(perms)

        self.url_list = reverse('livre-list')

    def get_token(self):
        return self.client.post(reverse('token_obtain_pair'), {
            'username': 'librarian', 'password': 'password123'
        }).data['access']

    def generate_image_file(self, name='test.jpg'):
        """
        Helper pour créer une vraie petite image valide en mémoire
        """
        file = io.BytesIO()
        image = Image.new('RGB', (100, 100), 'white')
        image.save(file, 'jpeg')
        file.name = name
        file.seek(0)
        return SimpleUploadedFile(name, file.read(), content_type='image/jpeg')

    def test_image_cleanup_on_delete(self):
        """
        Test: Supprimer un livre doit supprimer son image du disque.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. Création d'un livre avec image
        image = self.generate_image_file()
        data = {
            'nom': 'Livre à supprimer', 'date_sortie': '2023-01-01', 'nombre_pages': 100,
            'synopsis': 'Test', 'isbn': '1111111111111',
            'image': image
        }
        response = self.client.post(self.url_list, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        livre = Livre.objects.get(id=response.data['id'])
        path_image = livre.image.path
        
        # Vérification 1 : L'image existe bien sur le disque
        self.assertTrue(os.path.exists(path_image), "L'image devrait exister sur le disque")

        # 2. Suppression du livre
        url_detail = reverse('livre-detail', args=[livre.id])
        self.client.delete(url_detail)

        # Vérification 2 : L'image ne doit PLUS exister
        self.assertFalse(os.path.exists(path_image), "L'image aurait dû être supprimée avec le livre")

    def test_image_replacement(self):
        """
        Test: Remplacer l'image d'un livre doit supprimer l'ancienne.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 1. Création avec Image A
        image_a = self.generate_image_file('image_A.jpg')
        data = {
            'nom': 'Livre Update', 'date_sortie': '2023-01-01', 'nombre_pages': 100,
            'synopsis': 'Test', 'isbn': '2222222222222',
            'image': image_a
        }
        response = self.client.post(self.url_list, data, format='multipart')
        livre = Livre.objects.get(id=response.data['id'])
        path_image_a = livre.image.path

        self.assertTrue(os.path.exists(path_image_a))

        # 2. Mise à jour avec Image B
        image_b = self.generate_image_file('image_B.jpg')
        # Note: Pour l'upload de fichiers en PUT/PATCH, utiliser format='multipart' est crucial
        self.client.patch(
            reverse('livre-detail', args=[livre.id]), 
            {'image': image_b}, 
            format='multipart'
        )

        livre.refresh_from_db()
        path_image_b = livre.image.path

        # Vérification : L'ancienne est partie, la nouvelle est là
        self.assertFalse(os.path.exists(path_image_a), "L'ancienne image A devrait être supprimée")
        self.assertTrue(os.path.exists(path_image_b), "La nouvelle image B devrait exister")
        self.assertNotEqual(path_image_a, path_image_b)

    def test_invalid_file_upload(self):
        """
        Test: Uploader un fichier texte à la place d'une image doit être rejeté.
        """
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # On crée un faux fichier texte
        fichier_texte = SimpleUploadedFile("hack.txt", b"ceci n'est pas une image", content_type="text/plain")

        data = {
            'nom': 'Livre Hack', 'date_sortie': '2023-01-01', 'nombre_pages': 100,
            'synopsis': 'Test', 'isbn': '3333333333333',
            'image': fichier_texte
        }

        response = self.client.post(self.url_list, data, format='multipart')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        
        self.assertIn('image', response.data)
        # Le message typique est "Upload a valid image. The file you uploaded was either not an image or a corrupted image."

class UserProfileTests(APITestCase):
    def setUp(self):
        # 1. Création d'un utilisateur MINEUR (15 ans)
        today = date.today()
        date_mineur = today - timedelta(days=365*15)
        
        self.password_initial = 'password123'
        self.user = User.objects.create_user(
            username='chameleon', 
            password=self.password_initial,
            date_naissance=date_mineur,
            cacher_pour_adulte=False # Important : Il veut voir, mais son âge le bloque
        )

        # 2. Création d'un contenu ADULTE
        self.tag_adulte = Tag.objects.create(tag="Gore", pour_adulte=True)
        self.livre_adulte = Livre.objects.create(
            nom="Livre Interdit", 
            date_sortie="2020-01-01", 
            nombre_pages=666, 
            synopsis="Pas pour les enfants",
            isbn="9780000000666"
        )
        self.livre_adulte.tags.add(self.tag_adulte)

        self.url_user_detail = reverse('user-detail', args=[self.user.id])
        self.url_livre_detail = reverse('livre-detail', args=[self.livre_adulte.id])
        self.url_token = reverse('token_obtain_pair')

    def get_token(self, password=None):
        pwd = password if password else self.password_initial
        resp = self.client.post(self.url_token, {
            'username': self.user.username, 'password': pwd
        })
        if 'access' in resp.data:
            return resp.data['access']
        return None

    def test_dynamic_age_access(self):
        """
        Vérifie qu'un utilisateur qui devient majeur accède IMMÉDIATEMENT 
        au contenu adulte sans devoir se reconnecter.
        """
        # 1. Connexion en tant que mineur
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 2. Vérification : Accès refusé au livre adulte (404 car filtré)
        resp = self.client.get(self.url_livre_detail)
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # 3. L'utilisateur modifie sa date de naissance pour devenir MAJEUR (20 ans)
        date_majeur = date.today() - timedelta(days=365*20)
        
        # PATCH sur son propre profil
        resp_update = self.client.patch(self.url_user_detail, {
            'date_naissance': date_majeur
        })
        self.assertEqual(resp_update.status_code, status.HTTP_200_OK)

        # 4. Vérification IMMÉDIATE : Accès autorisé au livre adulte
        # On utilise le MÊME token qu'au début (pas de reconnexion)
        resp_retry = self.client.get(self.url_livre_detail)
        
        # Cela doit passer car à chaque requête, Django relit l'utilisateur en base
        self.assertEqual(resp_retry.status_code, status.HTTP_200_OK)

    def test_password_change_security(self):
        """
        Vérifie que le changement de mot de passe invalide l'ancien mot de passe
        pour les futures connexions.
        """
        # 1. Connexion initiale pour avoir le droit de modifier le profil
        token = self.get_token()
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + token)

        # 2. Changement de mot de passe via l'API
        new_password = 'new_secure_password_456'
        resp = self.client.patch(self.url_user_detail, {
            'password': new_password
        })
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # 3. Tentative de connexion avec l'ANCIEN mot de passe -> Doit échouer
        resp_old = self.client.post(self.url_token, {
            'username': self.user.username, 'password': self.password_initial
        })
        self.assertEqual(resp_old.status_code, status.HTTP_401_UNAUTHORIZED)

        # 4. Tentative de connexion avec le NOUVEAU mot de passe -> Doit réussir
        resp_new = self.client.post(self.url_token, {
            'username': self.user.username, 'password': new_password
        })
        self.assertEqual(resp_new.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp_new.data)