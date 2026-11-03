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
        *([Paragraph(f"{p.nom_legal}" + (f" — NEQ {p.neq}" if p.neq else "") + (f" — {p.adresse_legale}" if p.adresse_legale else ""), s["Normal"])] if p.nom_legal else []),
        *([Paragraph(" · ".join(x for x in [f"TPS/TVH : {p.numero_tps}" if p.numero_tps else "", f"TVQ : {p.numero_tvq}" if p.numero_tvq else ""] if x), s["Normal"])] if (p.numero_tps or p.numero_tvq) else []),
        Spacer(1, 10 * mm),
        Paragraph(f"<b>Reçu {paiement.numero_recu}</b>", s["Heading2"]),
        Paragraph(f"Date : {timezone.localtime(paiement.paye_le or paiement.cree_le):%d/%m/%Y %H:%M}", s["Normal"]),
        Paragraph(f"Client : {b.client or '—'} ({b.client.email if b.client else ''})", s["Normal"]),
        Spacer(1, 6 * mm),
    ]
    lignes = [
        ["Numéro de suivi", b.numero_suivi],
        ["Trajet", f"{v.ville_depart} → {b.ville_livraison}"],
        ["Départ", f"{timezone.localtime(v.depart):%d/%m/%Y %H:%M}"],
        ["Contenu", b.description],
        ["Destinataire", b.dest_nom],
        ["Frais fixes", f"{b.frais_fixes} {b.devise}"],
        [f"Poids facturé : {b.poids_a_facturer} kg"
         + (f" (volumétrique ; réel {b.poids} kg)" if b.volumetrique_applique else "")
         + f" × {b.tarif_kg} {b.devise}/kg", f"{(b.poids_a_facturer * b.tarif_kg).quantize(b.frais_fixes)} {b.devise}"],
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
                 Paragraph(f"Mode de paiement : {paiement.get_mode_display()} · Référence : {paiement.reference_stripe or '—'}", s["Normal"])]
    if paiement.mode == "carte":
        elements.append(Paragraph("Paiement par carte traité par Stripe. Aucune donnée de carte n'est conservée.", s["Italic"]))
    else:
        elements.append(Paragraph(f"Payé au comptoir{' — encaissé par ' + str(paiement.encaisse_par) if paiement.encaisse_par else ''}.", s["Italic"]))
    from .services import url_absolue
    from django.urls import reverse
    elements += [Spacer(1, 6 * mm),
                 Paragraph(f"<b>Suivez votre bagage :</b> {url_absolue(reverse('suivi_detail', args=[b.numero_suivi]))}", s["Normal"]),
                 Paragraph(f"<b>Code de remise à transmettre au destinataire :</b> {b.code_remise}", s["Normal"]),
                 Paragraph(f"Conditions générales : {url_absolue(reverse('conditions'))}", s["Normal"])]
    doc.build(elements)
    return tampon.getvalue()


def etiquette_pdf(bagage):
    """Étiquette 100 × 150 mm à coller sur le bagage : numéro, code QR (scanné au chargement), destination."""
    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing
    from reportlab.pdfgen import canvas

    from .templatetags.outils import tz

    L, H = 100 * mm, 150 * mm
    p = Parametres.charger()
    b, v = bagage, bagage.voyage
    tampon = BytesIO()
    c = canvas.Canvas(tampon, pagesize=(L, H))
    c.setTitle(f"Étiquette {b.numero_suivi}")
    c.setFillColor(BLEU)
    c.rect(0, H - 22 * mm, L, 22 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(8 * mm, H - 12 * mm, p.nom_entreprise)
    c.setFont("Helvetica", 8.5)
    c.drawString(8 * mm, H - 18 * mm, f"{p.telephone} · {p.courriel}")
    # Code QR = numéro de suivi (le transporteur le scanne au chargement)
    taille = 58 * mm
    qr = QrCodeWidget(b.numero_suivi, barLevel="M")
    x1, y1, x2, y2 = qr.getBounds()
    dessin = Drawing(taille, taille, transform=[taille / (x2 - x1), 0, 0, taille / (y2 - y1), 0, 0])
    dessin.add(qr)
    renderPDF.draw(dessin, c, (L - taille) / 2, H - 24 * mm - taille)
    c.setFillColor(colors.black)
    c.setFont("Courier-Bold", 19)
    c.drawCentredString(L / 2, H - 90 * mm, b.numero_suivi)
    c.setStrokeColor(colors.HexColor("#c8d3e0"))
    c.line(8 * mm, H - 95 * mm, L - 8 * mm, H - 95 * mm)
    ville = b.ville_livraison
    lignes = [
        ("DESTINATION", f"{ville.nom.upper()} ({ville.pays.code})", 15),
        ("DESTINATAIRE", b.dest_nom, 11),
        ("DÉPART", f"{v.ville_depart.nom} · {tz(v.depart, v.pays_depart.fuseau):%d/%m/%Y}", 11),
        ("POIDS", f"{b.poids} kg", 11),
    ]
    y = H - 103 * mm
    for libelle, valeur, taille_police in lignes:
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.HexColor("#66778a"))
        c.drawString(8 * mm, y, libelle)
        c.setFont("Helvetica-Bold", taille_police)
        c.setFillColor(colors.black)
        c.drawString(8 * mm, y - 5.5 * mm, valeur[:34])
        y -= 12 * mm
    c.showPage()
    c.save()
    return tampon.getvalue()
