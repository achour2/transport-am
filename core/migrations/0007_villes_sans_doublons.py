# Fusionne les villes en double (ex. « tizi ouzou » et « Tizi-Ouzou ») puis interdit les doublons.
import re
import unicodedata

from django.db import migrations, models


def normaliser(nom):
    nom = unicodedata.normalize("NFD", nom or "")
    nom = "".join(c for c in nom if unicodedata.category(c) != "Mn").lower()
    return re.sub(r"[\s\-_'’.]+", " ", nom).strip()


def fusionner_doublons(apps, schema_editor):
    Ville = apps.get_model("core", "Ville")
    Voyage = apps.get_model("core", "Voyage")
    Bagage = apps.get_model("core", "Bagage")
    groupes = {}
    for v in Ville.objects.all().order_by("pk"):
        v.nom = " ".join((v.nom or "").split())
        v.nom_normalise = normaliser(v.nom)
        groupes.setdefault((v.pays_id, v.nom_normalise), []).append(v)
    for villes in groupes.values():
        # On garde la ville avec des coordonnées, puis celle dont le nom a des majuscules (« Tizi-Ouzou »)
        villes.sort(key=lambda v: (v.latitude is None, v.nom == v.nom.lower(), v.pk))
        garde, doublons = villes[0], villes[1:]
        garde.save()
        for d in doublons:
            Voyage.objects.filter(ville_depart=d).update(ville_depart=garde)
            Voyage.objects.filter(ville_arrivee=d).update(ville_arrivee=garde)
            Bagage.objects.filter(ville_destination=d).update(ville_destination=garde)
            for voyage in Voyage.objects.filter(autres_villes=d):
                voyage.autres_villes.remove(d)
                if voyage.ville_arrivee_id != garde.pk:
                    voyage.autres_villes.add(garde)
            d.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0006_plan_lancement"),
    ]

    operations = [
        migrations.AlterUniqueTogether(name="ville", unique_together=set()),
        migrations.AddField(
            model_name="ville",
            name="nom_normalise",
            field=models.CharField(default="", editable=False, max_length=80),
        ),
        migrations.RunPython(fusionner_doublons, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="ville",
            constraint=models.UniqueConstraint(fields=("pays", "nom_normalise"), name="ville_unique_par_pays"),
        ),
    ]
