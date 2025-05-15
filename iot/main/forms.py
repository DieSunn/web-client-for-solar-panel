from django import forms
from django.db import connections

class HubForm(forms.Form):
    id_hub = forms.CharField(label='Идентификатор хаба', max_length=50)
    ip_address = forms.GenericIPAddressField(label='IP-адрес')
    port = forms.IntegerField(label='Порт')
    panel_count = forms.IntegerField(label='Количество панелей', min_value=1)
    panel_prefix = forms.CharField(label='Префикс названия панели', max_length=30)
    panel_type = forms.ChoiceField(label='Тип панели', choices=[('static','Статическая'), ('rotary','Вращающаяся')])

    def clean_id_hub(self):
        id_hub = self.cleaned_data['id_hub']
        conn = connections['solar_panel_db']
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM hub WHERE id_hub = %s", [id_hub])
            if cursor.fetchone():
                raise forms.ValidationError('Хаб с таким идентификатором уже существует')
        return id_hub

    def clean_panel_prefix(self):
        prefix = self.cleaned_data['panel_prefix']
        # проверка: нет панелей с таким префиксом
        conn = connections['solar_panel_db']
        with conn.cursor() as cursor:
            cursor.execute("SELECT id_panel FROM id_panel WHERE id_panel LIKE %s", [prefix + '%'])
            if cursor.fetchone():
                raise forms.ValidationError('Панели с данным префиксом уже существуют')
        return prefix
