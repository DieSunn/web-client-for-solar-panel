# forms.py
from django import forms
from django.db import connections
from django.db.models import UniqueConstraint # Необходимо для PanelData в моделях

# Предполагается, что модели Hub, Panel, PanelType, PanelStatus, PanelData определены в models.py
# и доступны здесь (например, через from .models import Hub, Panel, PanelType)
# Если они в другом месте, вам нужно будет импортировать их соответствующим образом.
# Для простоты, я предполагаю, что forms.py находится в том же приложении, что и models.py.
# Если нет, замените 'from .models import ...' на 'from your_app_name.models import ...'
from .models import Hub, Panel, PanelType # Импортируем только нужные модели для формы

class HubForm(forms.Form):
    """
    Форма для создания и редактирования хабов.
    Адаптирована для проверки уникальности id_hub с учетом случая редактирования.
    """
    id_hub = forms.CharField(label='Идентификатор хаба', max_length=50)
    ip_address = forms.GenericIPAddressField(label='IP-адрес')
    port = forms.IntegerField(label='Порт')
    panel_count = forms.IntegerField(label='Количество панелей', min_value=1,
                                     help_text="Используется только при создании хаба. При редактировании изменение количества панелей не поддерживается через эту форму.")
    panel_prefix = forms.CharField(label='Префикс названия панели', max_length=30,
                                    help_text="Используется только при создании хаба.")
    panel_type = forms.ChoiceField(label='Тип панели', choices=PanelType.choices) # Используем choices из PanelType

    def __init__(self, *args, **kwargs):
        # instance будет передан, если форма используется для редактирования
        self.instance = kwargs.pop('instance', None)
        super().__init__(*args, **kwargs)

        # При редактировании делаем поля count и prefix необязательными и невидимыми,
        # так как логика изменения количества панелей более сложна и не в рамках этой формы
        if self.instance:
            self.fields['panel_count'].required = False
            self.fields['panel_count'].widget = forms.HiddenInput()
            self.fields['panel_prefix'].required = False
            self.fields['panel_prefix'].widget = forms.HiddenInput()
            # При редактировании, если хотим запретить изменение id_hub, можно сделать его readonly
            # self.fields['id_hub'].widget.attrs['readonly'] = True


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

    def clean_panel_prefix(self):
        """
        Валидация префикса панели.
        Эта проверка актуальна только при создании нового хаба.
        """
        prefix = self.cleaned_data['panel_prefix']
        
        # Если это режим редактирования, то эту проверку можно пропустить
        if self.instance:
            return prefix

        conn = connections['solar_panel_db']
        with conn.cursor() as cursor:
            cursor.execute("SELECT id_panel FROM id_panel WHERE id_panel LIKE %s", [prefix + '%'])
            if cursor.fetchone():
                raise forms.ValidationError('Панели с данным префиксом уже существуют.')
        return prefix

