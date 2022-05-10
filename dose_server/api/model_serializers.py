from email.policy import default
from rest_framework import serializers
from api import models, utility
import typing

class UserUUIDRelatedField(serializers.RelatedField):
        def to_representation(self, value : models.User):
                return str(value.uuid)

class ApiSerializer(serializers.Serializer):

        def get_data(self, fields : typing.List[str] = []):
                if len(fields) == 0:
                        return self.data

                return { key:value for key, value in self.data.items() if key in fields }

class EntrySerializer(ApiSerializer):

        owner_uuid = UserUUIDRelatedField(source="owner", queryset=models.User.objects.all())

        start_datetime = serializers.DateTimeField()
        end_datetime = serializers.DateTimeField()

        blood_glucose = serializers.FloatField()
        trend_rate = serializers.FloatField()
        trend = serializers.CharField()

        insulin_on_board = serializers.ListField(child=serializers.FloatField(default=0), default=list)

        dosed_insulin = serializers.FloatField()
        dose_completion_time = serializers.DateTimeField()
        dose_target_bg = serializers.FloatField()