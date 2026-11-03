"""Double authentification des administrateurs (application Google Authenticator, Microsoft Authenticator…)."""
from io import BytesIO

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice


def _qr_svg(url):
    import qrcode
    import qrcode.image.svg

    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, box_size=9)
    tampon = BytesIO()
    img.save(tampon)
    return tampon.getvalue().decode()


@login_required
def deux_facteurs(request):
    user = request.user
    suivant = request.GET.get("next") or request.POST.get("next") or "/gestion/"
    if not url_has_allowed_host_and_scheme(suivant, {request.get_host()}):
        suivant = "/gestion/"
    if user.role != "admin" or user.is_verified():
        return redirect(suivant)
    appareil = TOTPDevice.objects.filter(user=user, confirmed=True).first()
    configuration = appareil is None
    if configuration:
        appareil = TOTPDevice.objects.filter(user=user, confirmed=False).first() or TOTPDevice.objects.create(
            user=user, name="Application d'authentification", confirmed=False)
    if request.method == "POST":
        code = (request.POST.get("code") or "").replace(" ", "")
        if code.isdigit() and appareil.verify_token(code):
            if configuration:
                appareil.confirmed = True
                appareil.save(update_fields=["confirmed"])
            otp_login(request, appareil)
            messages.success(request, "Double authentification validée.")
            return redirect(suivant)
        messages.error(request, "Code incorrect ou expiré. Utilisez le code affiché en ce moment dans l'application.")
    ctx = {"configuration": configuration, "next": suivant}
    if configuration:
        import base64

        ctx["qr"] = _qr_svg(appareil.config_url)
        ctx["cle"] = base64.b32encode(appareil.bin_key).decode()
    return render(request, "comptes/deux_facteurs.html", ctx)
