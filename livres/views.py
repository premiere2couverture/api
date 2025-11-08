from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.core.exceptions import PermissionDenied
from .forms import LivreForm, AuteurForm, TagForm, SearchForm, SearchLivreForm, SearchLectureForm, LectureForm, MarquePagesForm, UserForm, UserUpdateForm, CustomPasswordChangeForm, StatutLectureForm, DateDebutLectureForm, DateFinLectureForm, NoteLectureForm, CommentaireLectureForm
from api.models import Livre, Auteur, Tag, Lecture, User
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import Group
from django.views.decorators.http import require_POST
from api.utils import est_majeur
from django.contrib import messages
from django.db.models import Avg
from django.http import JsonResponse

def signup(request):
    if request.method == 'POST':
        form = UserForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('livres:login')
    else:
        form = UserForm()
    return render(request, 'auth/signup.html', {'form': form})

@login_required
def account(request):
    return render(request, 'user/account.html')

@login_required
def modifier_utilisateur(request):
    if request.method == 'POST':
        form = UserUpdateForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            return redirect('livres:account')
    else:
        form = UserUpdateForm(instance=request.user)
    return render(request, 'user/modifier_account.html', {'form': form})

@login_required
def change_password(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            return redirect('livres:account')
    else:
        form = CustomPasswordChangeForm(request.user)
    return render(request, 'user/change_password.html', {'form': form})

@login_required
def supprimer_account(request):
    if request.method == 'POST':
        request.user.delete()
        redirect('livres:rechercher')
    return redirect(reverse('livres:account'))

@permission_required('auth.view_group')
def group_list(request):
    groups = Group.objects.all().prefetch_related('user_set', 'permissions')
    context = {
        'groups': groups,
    }
    return render(request, 'admin/group_list.html', context)

@permission_required('auth.change_group')
def manage_group_users(request, group_id):
    group = get_object_or_404(Group, id=group_id)
    users_in_group = group.user_set.all()
    users_not_in_group = User.objects.exclude(groups=group)
    
    context = {
        'group': group,
        'users_in_group': users_in_group,
        'users_not_in_group': users_not_in_group,
    }
    return render(request, 'admin/manage_group_users.html', context)

@require_POST
@permission_required('auth.change_group')
def add_user_to_group(request, group_id, user_id):
    group = get_object_or_404(Group, id=group_id)
    user = get_object_or_404(User, id=user_id)
    
    if user not in group.user_set.all():
        group.user_set.add(user)
        messages.success(request, f'{user.username} ajouté au groupe {group.name}')
    else:
        messages.warning(request, f'{user.username} est déjà dans le groupe {group.name}')
    
    return redirect('livres:manage_group_users', group_id=group_id)

@require_POST
@permission_required('auth.change_group')
def remove_user_from_group(request, group_id, user_id):
    group = get_object_or_404(Group, id=group_id)
    user = get_object_or_404(User, id=user_id)
    
    if user in group.user_set.all():
        group.user_set.remove(user)
        messages.success(request, f'{user.username} retiré du groupe {group.name}')
    else:
        messages.warning(request, f'{user.username} n\'est pas dans le groupe {group.name}')
    
    return redirect('livres:manage_group_users', group_id=group_id)

@require_POST
@permission_required('auth.change_group')
def ajax_toggle_user_group(request, group_id, user_id):
    group = get_object_or_404(Group, id=group_id)
    user = get_object_or_404(User, id=user_id)
    
    if user in group.user_set.all():
        group.user_set.remove(user)
        action = 'removed'
        message = f'{user.username} retiré du groupe {group.name}'
    else:
        group.user_set.add(user)
        action = 'added'
        message = f'{user.username} ajouté au groupe {group.name}'
    
    return JsonResponse({
        'success': True,
        'action': action,
        'message': message,
        'user_id': user_id,
        'group_id': group_id
    })

def lister_livres(request):
    if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
        livres = Livre.objects.prefetch_related('auteurs')
    else:
        livres = Livre.objects.exclude(tags__pour_adulte=True).prefetch_related('auteurs')
    if request.method == 'POST':
        search_form = SearchLivreForm(request.POST)
        if search_form.is_valid():
            recherche = search_form.cleaned_data['recherche']
            tags_recherche = search_form.cleaned_data['tags']
            auteur_recherche = search_form.cleaned_data['auteur']
            if recherche == "":
                if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
                    livres = Livre.objects.prefetch_related('auteurs')
                else:
                    livres = Livre.objects.exclude(tags__pour_adulte=True).prefetch_related('auteurs')
            else:
                if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
                    livres = Livre.objects.filter(nom__icontains=recherche).prefetch_related('auteurs')
                else:
                    livres = Livre.objects.exclude(tags__pour_adulte=True).filter(nom__icontains=recherche).prefetch_related('auteurs')
            if len(tags_recherche)>0:
                for tag_recherche in tags_recherche:
                    if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
                        livres = Livre.objects.filter(tags__id=tag_recherche.id).distinct().prefetch_related('auteurs')
                    else:
                        livres = Livre.objects.exclude(tags__pour_adulte=True).filter(tags__id=tag_recherche.id).distinct().prefetch_related('auteurs')
            if auteur_recherche:
                if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
                    livres = Livre.objects.filter(auteurs__id=auteur_recherche.id).prefetch_related('auteurs')
                else:
                    livres = Livre.objects.exclude(tags__pour_adulte=True).filter(auteurs__id=auteur_recherche.id).prefetch_related('auteurs')
    else:
        search_form = SearchLivreForm()
    return render(request, 'livres/liste_livres.html', {'livres': livres, 'search_form': search_form})

def detail_livre(request, id):
    livre = get_object_or_404(Livre, id=id)
    if len(livre.tags.filter(pour_adulte=True))>0 and (not request.user.is_authenticated or not est_majeur(request.user) or request.user.cacher_pour_adulte):
        raise PermissionDenied("Vous ne pouvez pas voir ce contenu.")
    auteurs = livre.auteurs.all()
    tags = livre.tags.all()
    bouton_ajouter = True
    lecture = None
    souhait = False
    marque_pages_form = None
    statut_lecture_form = None
    date_debut_lecture_form = None
    date_fin_lecture_form = None
    note_lecture_form = None
    commentaire_lecture_form = None
    pages_restantes = None

    if request.user.is_authenticated:
        if len(Lecture.objects.filter(lecteur=request.user, livre=livre))!=0:
            lecture = Lecture.objects.filter(lecteur=request.user, livre=livre).first()
            marque_pages_form = MarquePagesForm(instance=lecture)
            statut_lecture_form = StatutLectureForm(instance=lecture)
            date_debut_lecture_form = DateDebutLectureForm(instance=lecture)
            date_fin_lecture_form = DateFinLectureForm(instance=lecture)
            note_lecture_form = NoteLectureForm(instance=lecture)
            commentaire_lecture_form = CommentaireLectureForm(instance=lecture)
            pages_restantes = None
            if lecture.marque_pages:
                pages_restantes = lecture.livre.nombre_pages - lecture.marque_pages
            bouton_ajouter = False
        if livre in Livre.objects.filter(user=request.user):
            souhait = True

    moyenne = Lecture.objects.filter(livre=livre, note__isnull=False).aggregate(moyenne=Avg('note'))['moyenne']
    if moyenne:
        moyenne = round(moyenne, 1)

    return render(request, 'livres/detail_livre.html', {
        'livre': livre, 
        'auteurs': auteurs, 
        'tags': tags, 
        'bouton_ajouter': bouton_ajouter, 
        'lecture': lecture, 
        'souhait': souhait, 
        'moyenne': moyenne,
        'marque_pages_form': marque_pages_form,
        'statut_lecture_form': statut_lecture_form,
        'date_debut_lecture_form': date_debut_lecture_form,
        'date_fin_lecture_form': date_fin_lecture_form,
        'note_lecture_form': note_lecture_form,
        'commentaire_lecture_form': commentaire_lecture_form,
        'pages_restantes': pages_restantes
    })

@permission_required('api.creer_livre')
def creer_livre(request):
    if request.method == 'POST':
        livre_form = LivreForm(request.POST, request.FILES)
        if livre_form.is_valid():
            livre = livre_form.save()
            return redirect('livres:detail_livre', id=livre.id)
    else:
        livre_form = LivreForm()
    return render(request, 'livres/creer_livre.html', {'form': livre_form})

@permission_required('api.modifier_livre')
def modifier_livre(request, id):
    livre = get_object_or_404(Livre, id=id)
    if len(livre.tags.filter(pour_adulte=True))>0 and (not request.user.is_authenticated or not est_majeur(request.user) or request.user.cacher_pour_adulte):
        raise PermissionDenied("Vous ne pouvez pas voir ce contenu.")
    livre_form = LivreForm(instance=livre)
    if request.method == 'POST':
        livre_form = LivreForm(request.POST, request.FILES, instance=livre)
        if livre_form.has_changed() and livre_form.is_valid():
            livre_form.save()
            return redirect('livres:detail_livre', id=id)
    return render(request, 'livres/modifier_livre.html', {'livre': livre, 'form': livre_form})

@permission_required('api.supprimer_livre')
def supprimer_livre(request, id):
    if request.method == "POST":
        livre = get_object_or_404(Livre, id=id)
        livre.delete()
        return redirect('livres:rechercher')
    return redirect(reverse('livres:detail_livre', args=[id]))

def liste_auteurs(request):
    auteurs = Auteur.objects.all()
    if request.method == 'POST':
        search_form = SearchForm(request.POST)
        if search_form.is_valid():
            recherche = search_form.cleaned_data['recherche']
            if recherche == "":
                auteurs = Auteur.objects.all()
            else:
                auteurs = Auteur.objects.filter(nom__icontains=recherche)
    else:
        search_form = SearchForm()
    return render(request, 'auteurs/liste_auteurs.html', {'auteurs': auteurs, 'search_form': search_form})

def detail_auteur(request, id):
    auteur = get_object_or_404(Auteur, id=id)
    if request.user.is_authenticated and est_majeur(request.user) and not request.user.cacher_pour_adulte:
        livres = Livre.objects.filter(auteurs__id=auteur.id)
    else:
        livres = Livre.objects.exclude(tags__pour_adulte=True).filter(auteurs__id=auteur.id)
    return render(request, 'auteurs/detail_auteur.html', {'auteur': auteur, 'livres': livres})

@permission_required('api.creer_auteur')
def creer_auteur(request):
    if request.method == 'POST':
        auteur_form = AuteurForm(request.POST)
        if auteur_form.is_valid():
            auteur = auteur_form.save()
            return redirect('livres:detail_auteur', id=auteur.id)
    else:
        auteur_form = AuteurForm()
    return render(request, 'auteurs/creer_auteur.html', {'form': auteur_form})

@permission_required('api.modifier_auteur')
def modifier_auteur(request, id):
    auteur = get_object_or_404(Auteur, id=id)
    auteur_form = AuteurForm(instance=auteur)
    if request.method == 'POST':
        auteur_form = AuteurForm(request.POST, instance=auteur)
        if auteur_form.has_changed() and auteur_form.is_valid():
            auteur_form.save()
            return redirect('livres:detail_auteur', id=id)
    return render(request, 'auteurs/modifier_auteur.html', {'auteur': auteur, 'form': auteur_form})

@permission_required('api.supprimer_livre')
def supprimer_auteur(request, id):
    if request.method == "POST":
        auteur = get_object_or_404(Auteur, id=id)
        auteur.delete()
        return redirect('livres:liste_auteurs')
    return redirect(reverse('livres:detail_auteur', args=[id]))

@permission_required('api.creer_tag')
def creer_tag(request):
    if request.method == 'POST':
        tag_form = TagForm(request.POST)
        if tag_form.is_valid():
            tag_form.save()
            return redirect('livres:liste_tags')
    else:
        tag_form = TagForm()
    return render(request, 'tags/creer_tag.html', {'form': tag_form})

def lister_tags(request):
    tags = Tag.objects.all()
    if request.method == 'POST':
        search_form = SearchForm(request.POST)
        if search_form.is_valid():
            recherche = search_form.cleaned_data['recherche']
            if recherche == "":
                tags = Tag.objects.all()
            else:
                tags = Tag.objects.filter(tag__icontains=recherche)
    else:
        search_form = SearchForm()
    return render(request, 'tags/liste_tags.html', {'tags': tags, 'search_form': search_form})

@permission_required('api.modifier_tag')
def modifier_tag(request, id):
    tag = get_object_or_404(Tag, id=id)
    tag_form = TagForm(instance=tag)
    if request.method == 'POST':
        if not tag.modifiable:
            raise PermissionDenied("Ce tag ne peut être modifié.")
        tag_form = TagForm(request.POST, instance=tag)
        if tag_form.has_changed() and tag_form.is_valid():
            tag_form.save()
            return redirect('livres:liste_tags')
    return render(request, 'tags/modifier_tag.html', {'tag': tag, 'form': tag_form})

@permission_required('api.supprimer_tag')
def supprimer_tag(request, id):
    tag = get_object_or_404(Tag, id=id)

    if not tag.modifiable:
        raise PermissionDenied("Ce tag ne peut être supprimé.")

    tag.delete()
    return redirect('livres:liste_tags')

@login_required
def bibliotheque(request):
    lectures = Lecture.objects.filter(lecteur=request.user)
    if request.method == 'POST':
        search_form = SearchLectureForm(request.POST)
        if search_form.is_valid():
            recherche = search_form.cleaned_data['recherche']
            statut = search_form.cleaned_data['statut']
            if recherche != "":
                lectures = lectures.filter(livre__nom__icontains=recherche)
            if statut != "":
                lectures = lectures.filter(statut=statut)
    else:
        search_form = SearchLectureForm()
    lectures_a_lire = lectures.filter(statut='a lire')
    lectures_lues = lectures.filter(statut='lu')
    lectures_en_cours = lectures.filter(statut='en cours')
    lectures_abandonnees = lectures.filter(statut='abandonne')
    lectures_en_pause = lectures.filter(statut='en pause')
    return render(request, 'lectures/bibliotheque.html', {'lectures': lectures, 'lectures_a_lire': lectures_a_lire, 'lectures_lues': lectures_lues, 'lectures_en_cours': lectures_en_cours, 'lectures_abandonnees': lectures_abandonnees, 'lectures_en_pause': lectures_en_pause, 'search_form': search_form})

@login_required
def ajouter_livre(request, id):
    livre = get_object_or_404(Livre, id=id)
    lecteur = request.user
    lecture = Lecture(
        statut="a lire",
        livre=livre,
        lecteur=lecteur
    )
    try:
        lecture.save()
    except:
        raise PermissionDenied(f"Impossible d'ajouer une nouvelle fois le livre {livre} pour {lecteur}.")
    return redirect('livres:detail_livre', id=id)

@login_required
def supprimer_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"{request.user} ne peut pas supprimer la lecture de {lecture.lecteur}.")

    lecture.delete()
    return redirect('livres:bibliotheque')

@login_required
def modifier_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)
    lecture_form = LectureForm(instance=lecture)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")

    if request.method == 'POST':
        lecture_form = LectureForm(request.POST, instance=lecture)
        if lecture_form.has_changed() and lecture_form.is_valid():
            lecture_form.save()
            return redirect('livres:detail_lecture', id=lecture.id)
    return render(request, 'lectures/modifier_lecture.html', {'lecture': lecture, 'form': lecture_form})

@login_required
def modifier_marque_pages(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")

    if request.method == 'POST':
        lecture_form = MarquePagesForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Marque-pages mis à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour du marque-pages.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def modifier_statut_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")
    
    if request.method == 'POST':
        lecture_form = StatutLectureForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Statut de lecture mis à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour du statut de lecture.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def modifier_date_debut_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")
    
    if request.method == 'POST':
        lecture_form = DateDebutLectureForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Date de début de lecture mise à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour de la date de début de lecture.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def modifier_date_fin_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")
    
    if request.method == 'POST':
        lecture_form = DateFinLectureForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Date de fin de lecture mise à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour de la date de fin de lecture.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def modifier_note_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")
    
    if request.method == 'POST':
        lecture_form = NoteLectureForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Note de la lecture mise à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour de la note de la lecture.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def modifier_commentaire_lecture(request, id):
    lecture = get_object_or_404(Lecture, id=id)

    if lecture.lecteur != request.user:
        raise PermissionDenied(f"Cette lecture n'appartient pas à {request.user}.")
    
    if request.method == 'POST':
        lecture_form = CommentaireLectureForm(request.POST, instance=lecture)
        if lecture_form.is_valid():
            lecture_form.save()
            messages.success(request, "Commentaire de la lecture mise à jour avec succès !")
        else:
            messages.error(request, "Erreur lors de la mise à jour du commentaire de la lecture.")

    return redirect('livres:detail_livre', id=lecture.livre.id)

@login_required
def ajouter_souhait(request, id):
    livre = get_object_or_404(Livre, id=id)

    if livre not in Livre.objects.filter(user=request.user):
        request.user.liste_de_souhaits.add(livre)

    return redirect('livres:detail_livre', id=livre.id)

@login_required
def retirer_souhait(request, id):
    livre = get_object_or_404(Livre, id=id)

    if livre in Livre.objects.filter(user=request.user):
        request.user.liste_de_souhaits.remove(livre)

    return redirect('livres:liste_de_souhaits')

@login_required
def liste_de_souhaits(request):
    livres = Livre.objects.filter(user=request.user)

    return render(request, 'liste_de_souhaits/liste_de_souhaits.html', {'livres': livres})
