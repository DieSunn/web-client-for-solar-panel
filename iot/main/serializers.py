from rest_framework import serializers
from .models import Solar_Panel, Characteristics

class SolarPanelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Solar_Panel
        fields = '__all__'

class CharacteristicsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Characteristics
        fields = '__all__'