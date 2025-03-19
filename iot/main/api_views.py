from rest_framework.views import APIView 
from rest_framework.response import Response 
from rest_framework import status 
from .models import Solar_Panel
from .serializers import PanelSerializer

class PanelListAPIView(APIView): 
    def get(self, request, format=None): 
        panels = Solar_Panel.objects.all() 
        serializer = PanelSerializer(panels, many=True) 
        return Response(serializer.data)

class PanelDetailAPIView(APIView): 
    def get(self, request, pk, format=None): 
        try: panel = Solar_Panel.objects.get(pk=pk) 
        except Solar_Panel.DoesNotExist: 
            return Response(status=status.HTTP_404_NOT_FOUND) 
        serializer = PanelSerializer(panel) 
        return Response(serializer.data)