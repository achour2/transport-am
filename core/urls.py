from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from .views import client, gestion, public, transporteur

urlpatterns = [
    # 6.1 Espace public
    path("", public.accueil, name="accueil"),
    path("robots.txt", public.robots_txt, name="robots_txt"),
    path("sitemap.xml", public.sitemap_xml, name="sitemap_xml"),
    path("taches/verifications/", public.taches_verifications, name="taches_verifications"),
    path("destinations/", public.destinations, name="destinations"),
    path("simulateur/", public.simulateur, name="simulateur"),
    path("simulateur/villes/", public.villes_pays, name="villes_pays"),
    path("suivi/", public.suivi, name="suivi"),
    path("suivi/<str:numero>/", public.suivi_detail, name="suivi_detail"),
    path("aide/", public.aide, name="aide"),
    path("conditions/", public.conditions, name="conditions"),
    path("connexion/", public.Connexion.as_view(), name="connexion"),
    path("deconnexion/", auth_views.LogoutView.as_view(), name="deconnexion"),
    path("inscription/", public.inscription, name="inscription"),
    path("confirmer/<str:jeton>/", public.confirmer_courriel, name="confirmer_courriel"),
    path("confirmer-renvoyer/", public.renvoyer_confirmation, name="renvoyer_confirmation"),
    path("mon-espace/", public.redirection_role, name="redirection_role"),
    path("mot-de-passe/oublie/", public.MotDePasseOublie.as_view(), name="mdp_oublie"),
    path("mot-de-passe/envoye/", auth_views.PasswordResetDoneView.as_view(template_name="comptes/mdp_envoye.html"), name="mdp_envoye"),
    path("mot-de-passe/nouveau/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="comptes/mdp_nouveau.html", success_url=reverse_lazy("mdp_termine")), name="password_reset_confirm"),
    path("mot-de-passe/termine/", auth_views.PasswordResetCompleteView.as_view(template_name="comptes/mdp_termine.html"), name="mdp_termine"),
    path("mot-de-passe/changer/", auth_views.PasswordChangeView.as_view(
        template_name="comptes/mdp_changer.html", success_url=reverse_lazy("redirection_role")), name="mdp_changer"),
    path("notifications/", public.notifications, name="notifications"),
    path("notifications/lues/", public.notifications_lues, name="notifications_lues"),
    path("notifications/<int:pk>/", public.notification_ouvrir, name="notification_ouvrir"),
    path("paiement/webhook/", client.stripe_webhook, name="stripe_webhook"),

    # 6.2 Espace client
    path("client/", client.tableau, name="client_tableau"),
    path("client/envoi/nouveau/", client.envoi_nouveau, name="client_envoi_nouveau"),
    path("client/envoi/nouveau/etape-<int:etape>/", client.envoi_nouveau, name="client_envoi_etape"),
    path("client/envoi/recommencer/", client.envoi_recommencer, name="client_envoi_recommencer"),
    path("client/envois/<str:numero>/", client.envoi_detail, name="client_envoi"),
    path("client/envois/<str:numero>/payer/", client.payer, name="client_payer"),
    path("client/envois/<str:numero>/paiement-retour/", client.paiement_retour, name="client_paiement_retour"),
    path("client/envois/<str:numero>/recu.pdf", client.recu, name="client_recu"),
    path("client/envois/<str:numero>/annuler/", client.annuler, name="client_annuler"),
    path("client/envois/<str:numero>/choix/", client.choix_voyage_annule, name="client_choix"),
    path("client/profil/", client.profil, name="client_profil"),
    path("client/profil/supprimer/", client.supprimer_compte, name="client_supprimer_compte"),

    # 6.3 Espace transporteur
    path("transporteur/", transporteur.voyages, name="transporteur_voyages"),
    path("transporteur/voyages/<int:pk>/", transporteur.voyage_detail, name="transporteur_voyage"),
    path("transporteur/position/", transporteur.position, name="transporteur_position"),
    path("transporteur/livraison/<str:numero>/", transporteur.livraison, name="transporteur_livraison"),

    # 6.4 Espace administrateur
    path("gestion/", gestion.tableau, name="gestion_tableau"),
    path("gestion/export.xlsx", gestion.export_excel, name="gestion_export"),
    path("gestion/pays/", gestion.pays_liste, name="gestion_pays"),
    path("gestion/pays/ajouter/", gestion.pays_form, name="gestion_pays_ajouter"),
    path("gestion/pays/<int:pk>/", gestion.pays_form, name="gestion_pays_modifier"),
    path("gestion/pays/<int:pk>/basculer/", gestion.pays_basculer, name="gestion_pays_basculer"),
    path("gestion/pays/<int:pk>/supprimer/", gestion.pays_supprimer, name="gestion_pays_supprimer"),
    path("gestion/voyages/", gestion.voyages, name="gestion_voyages"),
    path("gestion/voyages/creer/", gestion.voyage_form, name="gestion_voyage_creer"),
    path("gestion/voyages/<int:pk>/", gestion.voyage_form, name="gestion_voyage_modifier"),
    path("gestion/voyages/<int:dupliquer>/dupliquer/", gestion.voyage_form, name="gestion_voyage_dupliquer"),
    path("gestion/voyages/<int:pk>/annuler/", gestion.voyage_annuler, name="gestion_voyage_annuler"),
    path("gestion/bagages/", gestion.bagages, name="gestion_bagages"),
    path("gestion/bagages/comptoir/", gestion.envoi_comptoir, name="gestion_envoi_comptoir"),
    path("gestion/bagages/<str:numero>/recu.pdf", gestion.recu_admin, name="gestion_recu"),
    path("gestion/bagages/<str:numero>/", gestion.bagage_detail, name="gestion_bagage"),
    path("gestion/incidents/", gestion.incidents, name="gestion_incidents"),
    path("gestion/utilisateurs/", gestion.utilisateurs, name="gestion_utilisateurs"),
    path("gestion/messages/", gestion.messages_contact, name="gestion_messages"),
    path("gestion/parametres/", gestion.parametres, name="gestion_parametres"),
]
