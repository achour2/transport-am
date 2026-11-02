"""
Génère locale/{en,ar}/LC_MESSAGES/django.po et .mo sans dépendre de gettext.
Usage : python scripts/traductions.py
(Les chaînes non traduites s'affichent en français. Pour compléter : ajoutez-les ici,
ou utilisez `django-admin makemessages` + un outil comme Poedit.)
"""
import struct
from pathlib import Path

T = {
 "Actualiser": ("Refresh", "تحديث"),
 "Aide": ("Help", "مساعدة"),
 "Aller au contenu": ("Skip to content", "انتقل إلى المحتوى"),
 "Apportez votre bagage au point de dépôt avant la date limite.": ("Bring your luggage to the drop-off point before the deadline.", "أحضر أمتعتك إلى نقطة الإيداع قبل الموعد النهائي."),
 "Arrivée": ("Arrival", "الوصول"),
 "Arrivée prévue": ("Expected arrival", "الوصول المتوقع"),
 "Aucun départ planifié pour le moment. Revenez bientôt !": ("No departures scheduled yet. Check back soon!", "لا توجد رحلات مبرمجة حالياً. عد قريباً!"),
 "Aucun voyage disponible pour ce poids pour l’instant.": ("No trip available for this weight right now.", "لا توجد رحلة متاحة لهذا الوزن حالياً."),
 "Aucun événement pour le moment.": ("No events yet.", "لا توجد أحداث بعد."),
 "Aucune destination.": ("No destinations.", "لا توجد وجهات."),
 "Calculer": ("Calculate", "احسب"),
 "Carte du trajet": ("Route map", "خريطة المسار"),
 "Changer mon mot de passe": ("Change my password", "تغيير كلمة المرور"),
 "Choisissez le voyage, décrivez le bagage, payez par carte.": ("Pick the trip, describe the luggage, pay by card.", "اختر الرحلة، صف الأمتعة، وادفع بالبطاقة."),
 "Choisissez un pays et saisissez le poids : le prix s’affiche instantanément.": ("Choose a country and enter the weight: the price appears instantly.", "اختر بلداً وأدخل الوزن: يظهر السعر فوراً."),
 "Comment ça marche": ("How it works", "كيف يعمل"),
 "Complet": ("Full", "مكتمل"),
 "Conditions et confidentialité": ("Terms and privacy", "الشروط والخصوصية"),
 "Confirmez votre courriel pour sécuriser votre compte.": ("Confirm your email to secure your account.", "أكّد بريدك الإلكتروني لتأمين حسابك."),
 "Connexion": ("Log in", "تسجيل الدخول"),
 "Contact": ("Contact", "اتصل بنا"),
 "Courriel": ("Email", "البريد الإلكتروني"),
 "Courriel ou mot de passe incorrect.": ("Incorrect email or password.", "البريد الإلكتروني أو كلمة المرور غير صحيحة."),
 "Créer un compte": ("Create an account", "إنشاء حساب"),
 "Dernière position": ("Last position", "آخر موقع"),
 "Destinataire": ("Recipient", "المستلم"),
 "Destinations": ("Destinations", "الوجهات"),
 "Destinations et tarifs": ("Destinations and rates", "الوجهات والأسعار"),
 "Dimensions (optionnel)": ("Dimensions (optional)", "الأبعاد (اختياري)"),
 "Documents demandés à la douane": ("Documents required by customs", "الوثائق المطلوبة في الجمارك"),
 "Déconnexion": ("Log out", "تسجيل الخروج"),
 "Délai": ("Lead time", "المدة"),
 "Délai estimé": ("Estimated time", "المدة المقدرة"),
 "Départ": ("Departure", "المغادرة"),
 "Déposer": ("Drop off", "الإيداع"),
 "Envoyer un bagage": ("Send luggage", "أرسل أمتعة"),
 "Envoyez vos bagages entre pays": ("Send your luggage between countries", "أرسل أمتعتك بين البلدان"),
 "Envoyez vos bagages et colis entre le Canada, l’Algérie, la France, le Maroc et la Tunisie. Réservation en ligne, suivi en temps réel.": ("Ship luggage and parcels between Canada, Algeria, France, Morocco and Tunisia. Online booking, real-time tracking.", "أرسل أمتعتك وطرودك بين كندا والجزائر وفرنسا والمغرب وتونس. حجز عبر الإنترنت وتتبع مباشر."),
 "Filtrer par pays": ("Filter by country", "تصفية حسب البلد"),
 "Frais fixes": ("Fixed fee", "رسوم ثابتة"),
 "Gestion": ("Management", "الإدارة"),
 "Historique": ("History", "السجل"),
 "Ils nous font confiance": ("They trust us", "يثقون بنا"),
 "Kilos restants": ("Kilos left", "الكيلوغرامات المتبقية"),
 "La position du voyage s’affichera dès que le bagage sera en transit.": ("The trip position will show as soon as the luggage is in transit.", "سيظهر موقع الرحلة بمجرد أن تكون الأمتعة في الطريق."),
 "Le destinataire présente son code à 6 chiffres et récupère le bagage.": ("The recipient shows their 6-digit code and collects the luggage.", "يقدّم المستلم رمزه المكون من 6 أرقام ويستلم الأمتعة."),
 "Le numéro de suivi figure dans votre courriel de confirmation.": ("The tracking number is in your confirmation email.", "رقم التتبع موجود في بريد التأكيد."),
 "Lien copié": ("Link copied", "تم نسخ الرابط"),
 "Longueur × largeur × hauteur, en cm": ("Length × width × height, in cm", "الطول × العرض × الارتفاع، بالسنتيمتر"),
 "Ma position": ("My position", "موقعي"),
 "Max": ("Max", "الحد الأقصى"),
 "Menu": ("Menu", "القائمة"),
 "Mes voyages": ("My trips", "رحلاتي"),
 "Mon espace": ("My account", "حسابي"),
 "Mot de passe": ("Password", "كلمة المرور"),
 "Mot de passe oublié ?": ("Forgot password?", "نسيت كلمة المرور؟"),
 "Notifications": ("Notifications", "الإشعارات"),
 "Nouvel envoi": ("New shipment", "إرسال جديد"),
 "Numéro de suivi": ("Tracking number", "رقم التتبع"),
 "Objets interdits": ("Prohibited items", "المواد الممنوعة"),
 "Par kilo": ("Per kilo", "للكيلو"),
 "Partager le lien": ("Share link", "مشاركة الرابط"),
 "Pas encore de compte ?": ("No account yet?", "ليس لديك حساب؟"),
 "Pays desservis": ("Countries served", "البلدان المخدومة"),
 "Point de dépôt": ("Drop-off point", "نقطة الإيداع"),
 "Prix = frais fixes + (poids × tarif par kilo). Départs depuis le Canada.": ("Price = fixed fee + (weight × rate per kilo). Departures from Canada.", "السعر = رسوم ثابتة + (الوزن × السعر للكيلو). المغادرة من كندا."),
 "Prix total": ("Total price", "السعر الإجمالي"),
 "Prochain départ": ("Next departure", "المغادرة القادمة"),
 "Prochains départs": ("Upcoming departures", "المغادرات القادمة"),
 "Prochains voyages disponibles": ("Next available trips", "الرحلات المتاحة القادمة"),
 "Profil et préférences": ("Profile and preferences", "الملف الشخصي والتفضيلات"),
 "Progression du bagage": ("Luggage progress", "تقدم الأمتعة"),
 "Recevoir": ("Receive", "الاستلام"),
 "Renvoyer le lien": ("Resend link", "إعادة إرسال الرابط"),
 "Réserver": ("Book", "احجز"),
 "Réserver ce prix": ("Book at this price", "احجز بهذا السعر"),
 "Réserver vers ce pays": ("Book to this country", "احجز إلى هذا البلد"),
 "Réservez en moins de 3 minutes, déposez votre bagage, et suivez-le sur la carte jusqu’à sa remise au destinataire.": ("Book in under 3 minutes, drop off your luggage, and follow it on the map until it reaches the recipient.", "احجز في أقل من 3 دقائق، أودِع أمتعتك، وتابعها على الخريطة حتى تسليمها للمستلم."),
 "Saisissez le numéro de suivi reçu par courriel (ex. BG-7F3K9Q2A).": ("Enter the tracking number from your email (e.g. BG-7F3K9Q2A).", "أدخل رقم التتبع الذي وصلك بالبريد (مثال BG-7F3K9Q2A)."),
 "Se connecter": ("Log in", "دخول"),
 "Service": ("Service", "الخدمة"),
 "Simulateur": ("Price calculator", "حاسبة السعر"),
 "Simulateur de prix": ("Price calculator", "حاسبة السعر"),
 "Simuler": ("Estimate", "احسب السعر"),
 "Simuler un prix": ("Estimate a price", "احسب السعر"),
 "Suivez le trajet sur la carte, notifié à chaque étape.": ("Follow the route on the map, notified at every step.", "تابع المسار على الخريطة مع إشعار في كل مرحلة."),
 "Suivi": ("Tracking", "التتبع"),
 "Suivi en temps réel · Paiement sécurisé": ("Real-time tracking · Secure payment", "تتبع مباشر · دفع آمن"),
 "Suivre": ("Track", "تتبع"),
 "Suivre mon bagage": ("Track my luggage", "تتبع أمتعتي"),
 "Suivre un bagage": ("Track luggage", "تتبع أمتعة"),
 "S’abonner": ("Subscribe", "اشترك"),
 "Tous les pays": ("All countries", "كل البلدان"),
 "Toutes les destinations": ("All destinations", "كل الوجهات"),
 "Transport de bagages entre pays": ("Luggage transport between countries", "نقل الأمتعة بين البلدان"),
 "Un prix exact, avant même de créer un compte.": ("An exact price, before you even sign up.", "سعر دقيق قبل إنشاء حساب."),
 "Volume": ("Volume", "الحجم"),
 "Vos bagages arrivent. Vous savez où ils sont.": ("Your luggage arrives. You know where it is.", "أمتعتك تصل. وأنت تعرف أين هي."),
 "Vos bagages et colis entre le Canada et le Maghreb / l’Europe, suivis en temps réel.": ("Your luggage and parcels between Canada and North Africa / Europe, tracked in real time.", "أمتعتك وطرودك بين كندا والمغرب العربي / أوروبا، مع تتبع مباشر."),
 "frais fixes": ("fixed fee", "رسوم ثابتة"),
 "mise à jour": ("updated", "تم التحديث"),
 "restants": ("left", "متبقية"),
 "Être prévenu par courriel": ("Get email updates", "استلم الإشعارات بالبريد"),
 "à partir de": ("from", "ابتداءً من"),
 "à venir": ("coming soon", "قريباً"),
 # Statuts (modèles)
 "Enregistré": ("Registered", "مسجّل"),
 "Déposé": ("Dropped off", "تم الإيداع"),
 "Chargé": ("Loaded", "تم التحميل"),
 "En transit": ("In transit", "في الطريق"),
 "Arrivé à destination": ("Arrived at destination", "وصل إلى الوجهة"),
 "Arrivé": ("Arrived", "وصل"),
 "Livré": ("Delivered", "تم التسليم"),
 "Incident en cours": ("Incident in progress", "حادث قيد المعالجة"),
 "Perdu": ("Lost", "مفقود"),
 "Annulé": ("Cancelled", "ملغى"),
 "Planifié": ("Scheduled", "مبرمج"),
 "En cours": ("In progress", "جارية"),
 "Terminé": ("Completed", "منتهية"),
 "Avion": ("Plane", "طائرة"),
 "Camion": ("Truck", "شاحنة"),
 "Bateau": ("Ship", "سفينة"),
 # Espace client
 "Envois en cours": ("Shipments in progress", "الإرساليات الجارية"),
 "Nouvel envoi": ("New shipment", "إرسال جديد"),
 "Destination": ("Destination", "الوجهة"),
 "Bagage": ("Luggage", "الأمتعة"),
 "Paiement": ("Payment", "الدفع"),
 "Continuer": ("Continue", "متابعة"),
 "Retour": ("Back", "رجوع"),
 "Récapitulatif": ("Summary", "الملخص"),
 "Total": ("Total", "المجموع"),
 "Payer": ("Pay", "ادفع"),
 "Annuler": ("Cancel", "إلغاء"),
 "Reçu PDF": ("PDF receipt", "إيصال PDF"),
 "Code de remise à transmettre au destinataire": ("Handover code to give the recipient", "رمز التسليم لإعطائه للمستلم"),
 "Enregistrer": ("Save", "حفظ"),
 "Mettre à jour ma position": ("Update my position", "تحديث موقعي"),
}


def ecrire_mo(chemin, traductions):
    cles = sorted(traductions)
    ids = b""
    strs = b""
    offsets = []
    for k in cles:
        kb, vb = k.encode(), traductions[k].encode()
        offsets.append((len(ids), len(kb), len(strs), len(vb)))
        ids += kb + b"\0"
        strs += vb + b"\0"
    n = len(cles)
    debut_cles = 7 * 4
    debut_vals = debut_cles + n * 8
    debut_ids = debut_vals + n * 8
    debut_strs = debut_ids + len(ids)
    sortie = struct.pack("Iiiiiii", 0x950412DE, 0, n, debut_cles, debut_vals, 0, 0)
    for o, l, _, _ in offsets:
        sortie += struct.pack("ii", l, debut_ids + o)
    for _, _, o, l in offsets:
        sortie += struct.pack("ii", l, debut_strs + o)
    sortie += ids + strs
    chemin.write_bytes(sortie)


def echapper(s):
    return s.replace("\\", "\\\\").replace('"', '\\"')


racine = Path(__file__).resolve().parent.parent / "locale"
for i, langue in enumerate(("en", "ar")):
    d = racine / langue / "LC_MESSAGES"
    d.mkdir(parents=True, exist_ok=True)
    trad = {k: v[i] for k, v in T.items()}
    pluriel = "nplurals=2; plural=(n != 1);" if langue == "en" else "nplurals=6; plural=n==0 ? 0 : n==1 ? 1 : n==2 ? 2 : n%100>=3 && n%100<=10 ? 3 : n%100>=11 ? 4 : 5;"
    entete = f"Content-Type: text/plain; charset=UTF-8\nLanguage: {langue}\nPlural-Forms: {pluriel}\n"
    po = f'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n"Language: {langue}\\n"\n\n'
    po += "".join(f'msgid "{echapper(k)}"\nmsgstr "{echapper(v)}"\n\n' for k, v in sorted(trad.items()))
    (d / "django.po").write_text(po, encoding="utf-8")
    ecrire_mo(d / "django.mo", {"": entete, **trad})
    print(f"{langue}: {len(trad)} chaînes")
