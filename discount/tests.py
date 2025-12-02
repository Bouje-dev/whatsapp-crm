from django.http import JsonResponse
from django.shortcuts import render ,get_object_or_404
from .models import CustomUser , GroupMessages , groupchat
from django.contrib.auth.decorators import login_required

@login_required
def testing_Chanels(request):
    # grop = groupchat.objects.create( group_name = "Test Group Chtee123" ).save()
    # # grop.members.add( request.user )
    # buby = GroupMessages.objects.create(auther = request.user , Group = grop , message = "This is a test message from testing endpoint" )
    # buby.save()
    groupcha = get_object_or_404(groupchat, group_name="Test Group Chat")

    chat_messages = GroupMessages.objects.filter(Group=groupcha).order_by('created')
   

    return render( request, "testing.html", {'chat_name' :groupcha, 'chat_messages': chat_messages } )
import json
def send_msgtesting(request):
    if request.method == "POST":
        groupcha = get_object_or_404(groupchat, group_name="Test Group Chat")
        data = json.loads(request.body)
        message_text = data.get("message")

        
        if message_text:
            new_message = GroupMessages.objects.create(
                auther=request.user,
                Group=groupcha,
                message=message_text
            )
            new_message.save()
            if new_message:
                return JsonResponse({"status": "success"})
    return JsonResponse({"status": "success"})