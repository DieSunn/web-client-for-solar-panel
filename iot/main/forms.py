# forms.py
from django import forms
from django.db import connections

# Предполагается, что модели Hub, Panel, PanelType, PanelStatus, PanelData определены в models.py
# и доступны здесь (например, через from .models import Hub, Panel, PanelType)
from .models import Hub, Panel, PanelType # PanelType может понадобиться, если вы хотите его использовать для PanelForm

class HubForm(forms.Form):
    """
    Форма для создания и редактирования хабов.
    Теперь содержит только поля, относящиеся к самому хабу.
    Данные по панелям обрабатываются отдельно в представлении.
    """
    id_hub = forms.CharField(label='Идентификатор хаба', max_length=50)
    ip_address = forms.GenericIPAddressField(label='IP-адрес')
    port = forms.IntegerField(label='Порт')

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

    def clean_id_hub(self):
        """
        Проверка уникальности id_hub.
        Если форма используется для редактирования (т.е. self.instance существует)
        и id_hub не изменился, то проверка на уникальность не требуется.
        """
        id_hub = self.cleaned_data['id_hub']

        # Если это режим редактирования и id_hub не изменился
        if self.instance and self.instance.id_hub == id_hub:
            return id_hub

        # В противном случае, проверяем уникальность во вторичной БД
        conn = connections['solar_panel_db']
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM hub WHERE id_hub = %s", [id_hub])
            if cursor.fetchone():
                raise forms.ValidationError('Хаб с таким идентификатором уже существует.')
        return id_hub


class PanelInlineForm(forms.Form):
    """
    Вспомогательная форма для валидации данных одной динамически добавленной панели.
    Используется только для валидации данных, приходящих из POST-запроса,
    не для рендеринга полей формы в HTML.
    """
    id_panel = forms.CharField(label='Имя панели', max_length=50)
    coordinates = forms.CharField(label='Координаты (lat,lng)', max_length=100) # Будет проверяться regex в clean
    type = forms.ChoiceField(label='Тип панели', choices=PanelType.choices)

    def clean_coordinates(self):
        coords_str = self.cleaned_data['coordinates']
        # Проверяем формат "lat,lng" с помощью регулярного выражения
        import re
        if not re.match(r"^(-?\d+(\.\d+)?),\s*(-?\d+(\.\d+)?)$", coords_str):
            raise forms.ValidationError('Неверный формат координат. Ожидается: широта, долгота (например, 40.714, -74.005)')
        return coords_str

    # Удален метод clean_id_panel, так как его логика была слишком строгой
    # и не соответствовала требованию уникальности в пределах хаба.
    # Проверка уникальности id_panel в связке с id_hub теперь полагается
    # на ограничения базы данных и Django ORM.