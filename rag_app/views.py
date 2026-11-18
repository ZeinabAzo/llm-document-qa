from django.shortcuts import render

import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .ai_engine import ask_question
from .models import QAHistory


@csrf_exempt
def ask_api(request):
    """Handle POST requests with a JSON question, return the RAG answer, and log it."""
    if request.method != "POST":
        return JsonResponse({"error": "Only POST requests are allowed."}, status=405)

    try:
        body = json.loads(request.body)
        question = body.get("question", "").strip()
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if not question:
        return JsonResponse({"error": "The 'question' field is required."}, status=400)

    # Generate answer using the RAG pipeline
    answer = ask_question(question)

    # Save the interaction to QAHistory
    QAHistory.objects.create(question=question, answer=answer)

    return JsonResponse({"question": question, "answer": answer}, status=200)