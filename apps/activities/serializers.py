from rest_framework import serializers
from .models import UniversalActivity

class UniversalActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = UniversalActivity
        fields = '__all__'
