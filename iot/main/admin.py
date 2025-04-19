from django.contrib import admin
from .models import Solar_Panel, Characteristics, Hub, Panel, PanelData

admin.site.register(Solar_Panel)
admin.site.register(Characteristics)
admin.site.register(Hub)
admin.site.register(Panel)
admin.site.register(PanelData)