"""Génération du reçu PDF (ReportLab)."""
from io import BytesIO

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import Parametres

BLEU = colors.HexColor("#1f4e79")


def recu_pdf(paiement):
    p = Parametres.charger()
    b = paiement.bagage
    v = b.voyage
    tampon = BytesIO()
    doc = SimpleDocTemplate(tampon, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm,
                            title=f"Reçu {paiement.numero_recu}")
    s = getSampleStyleSheet()
    s["Title"].textColor = BLEU
    s["Title"].alignment = 0
    elements = [
        Paragraph(p.nom_entreprise, s["Title"]),
        Paragraph(f"{p.adresse_depot} · {p.telephone} · {p.courriel}", s["Normal"]),
        Spacer(1, 10 * mm),
        Paragraph(f"<b>Reçu {paiement.numero_recu}</b>", s["Heading2"]),
        Paragraph(f"Date : {timezone.localtime(paiement.paye_le or paiement.cree_le):%d/%m/%Y %H:%M}", s["Normal"]),
        Paragraph(f"Client : {b.client or '—'} ({b.client.email if b.client else ''})", s["Normal"]),
        Spacer(1, 6 * mm),
    ]
    lignes = [
        ["Numéro de suivi", b.numero_suivi],
        ["Trajet", f"{v.ville_depart} → {v.ville_arrivee}"],
        ["Départ", f"{timezone.localtime(v.depart):%d/%m/%Y %H:%M}"],
        ["Contenu", b.description],
        ["Destinataire", b.dest_nom],
        ["Frais fixes", f"{b.frais_fixes} {b.devise}"],
        [f"Poids : {b.poids} kg × {b.tarif_kg} {b.devise}/kg", f"{(b.poids * b.tarif_kg).quantize(b.frais_fixes)} {b.devise}"],
        ["TOTAL PAYÉ", f"{paiement.montant} {paiement.devise}"],
    ]
    if paiement.statut == "rembourse":
        lignes.append(["REMBOURSÉ LE", f"{timezone.localtime(paiement.rembourse_le):%d/%m/%Y}"])
    t = Table(lignes, colWidths=[75 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d3e0")),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef3f9")),
        ("FONTNAME", (0, 7), (-1, 7), "Helvetica-Bold"),
        ("BACKGROUND", (0, 7), (-1, 7), colors.HexColor("#dbe7f5")),
        ("PADDING", (0, 0), (-1, -1), 6),
    ]))
    elements += [t, Spacer(1, 8 * mm),
                 Paragraph(f"Référence de paiement : {paiement.reference_stripe or '—'}", s["Normal"]),
                 Paragraph("Paiement par carte traité par Stripe. Aucune donnée de carte n'est conservée.", s["Italic"])]
    doc.build(elements)
    return tampon.getvalue()
