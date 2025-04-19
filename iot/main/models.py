from django.db import models

#Данные вставляются в поля бд напрямую (ORM)
# Модель для представления солнечных панелей
class Solar_Panel(models.Model):
    id = models.IntegerField(primary_key=True)  # id установки
    ip_address = models.CharField(max_length=15, default='')  # адрес
    port = models.CharField(max_length=5, default='')  # порт установки
    coordinates = models.CharField(null=True, blank=True)  # координаты
    description = models.TextField(null=True, blank=True)  # описание
    type = models.TextField(null=True, blank=True)  # тип установки (поворотная/неповоротная)


    class Meta:
        ordering = ['-id'] # Сортировка по убыванию id при запросах к модели

    def __str__(self):
        return str(self.id) # Возвращаем строковое представление id установки


# Модель для хранения характеристик солнечных панелей
class Characteristics(models.Model):
    id = models.AutoField(primary_key=True)
    date = models.DateField()
    time = models.TimeField()
    generated_power = models.FloatField()
    consumed_power = models.FloatField()
    vertical_position = models.IntegerField()
    horizontal_position = models.IntegerField()
    status = models.TextField(null=True, blank=True)  # on off etc
    options = models.TextField(null=True, blank=True)  # в заметках
    weather = models.TextField(null=True, blank=True)  # берется с сайта
    battery = models.FloatField(null=True)  # заряд батареи

    solar_panel = models.ForeignKey(
        Solar_Panel, on_delete=models.RESTRICT, null=True, blank=True) # Связь с соответствующей солнечной панелью

    class Meta:
        ordering = ['-date', 'time'] # Сортировка по убыванию даты и возрастанию времени записи

    def __str__(self):
        return str(self.date) # Возвращаем строковое представление даты характеристики


# Модель для хранения заявлений и команд относительно солнечных панелей
class SolarStatement(models.Model):
    solar_panel = models.ForeignKey(Solar_Panel, on_delete=models.RESTRICT) # Связь с соответствующей солнечной панелью
    id = models.AutoField(primary_key=True)  # Уникальный идентификатор заявления
    statement = models.TextField() # Заявление
    command = models.TextField() # Команда
    date = models.DateTimeField() # Дата и время заявления

    class Meta:
        db_table = 'solar_statement' # Имя таблицы в базе данных

    def __str__(self):
        return f"Statement {self.id} from Solar {self.solar_panel}" # Возвращаем строковое представление заявления и связанной с ним солнечной панели

# PostgreSQL ENUM support via Django migrations (see custom migration below)
class Hub(models.Model):
    id_hub = models.CharField(max_length=50, primary_key=True)
    ip_address = models.CharField(max_length=50)
    port = models.IntegerField()

    class Meta:
        db_table = 'hub'
        verbose_name = 'Hub'
        verbose_name_plural = 'Hubs'

    def __str__(self):
        return self.id_hub


class PanelType(models.TextChoices):
    STATIC = 'static', 'Static'
    ROTARY = 'rotary', 'Rotary'


class Panel(models.Model):
    id_panel = models.CharField(max_length=50)
    hub = models.ForeignKey(Hub, on_delete=models.RESTRICT, db_column='id_hub')
    type = models.CharField(
        max_length=6,
        choices=PanelType.choices,
        default=PanelType.STATIC,
        db_column='type'
    )
    coordinates = models.CharField(null=True, blank=True)

    class Meta:
        db_table = 'id_panel'
        unique_together = (('id_panel', 'hub'),)
        verbose_name = 'Panel'
        verbose_name_plural = 'Panels'

    def __str__(self):
        return f"{self.id_panel} @ {self.hub_id}"


class PanelStatus(models.TextChoices):
    ON = 'on', 'On'
    OFF = 'off', 'Off'


class PanelData(models.Model):
    id = models.AutoField(primary_key=True)
    id_panel = models.CharField(max_length=50)
    id_hub = models.CharField(max_length=50)
    generated_power = models.FloatField()
    consumed_power = models.FloatField()
    vertical_position = models.FloatField()
    horizontal_position = models.FloatField()
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(
        max_length=3,
        choices=PanelStatus.choices,
        default=PanelStatus.ON,
        db_column='status'
    )
    battery_charge = models.FloatField(db_column='battery_charge')

    class Meta:
        db_table = 'panel_data'
        # composite foreign key not natively supported; enforce via migration or DB constraint
        verbose_name = 'Panel Data'
        verbose_name_plural = 'Panel Data Records'

    def __str__(self):
        return f"Data {self.id} for {self.id_panel}@{self.id_hub} on {self.date} {self.time}"
