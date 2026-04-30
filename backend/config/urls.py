from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthcheck(_request):
    return JsonResponse({'status': 'ok'})


def api_root(_request):
    return JsonResponse({
        'status': 'ok',
        'health': '/healthz/',
        'api': '/api/v1/',
    })


urlpatterns = [
    path('', api_root),
    path('healthz/', healthcheck),
    path('admin/', admin.site.urls),
    path('api/v1/', include('ledger.urls')),
]
