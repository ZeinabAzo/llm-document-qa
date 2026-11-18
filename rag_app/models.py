from django.db import models

# includes two tables: 1.Document 2.QAHistory

class Document(models.Model):
    # the first field: the word file we got from our user
    file = models.FileField(upload_to='documents/')
    
    # the second field of this table: 
    extracted_text = models.TextField(blank=True, null=True)
    
    # third field: uploaded time
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # just to show the name of this table cleaner in the management panel
    def __str__(self):
        return self.file.name


class QAHistory(models.Model):
    # 1. the question
    question = models.TextField()
    
    # 2. the answer ai creates
    answer = models.TextField()
    
    # 3. the time the user has prompted us
    asked_at = models.DateTimeField(auto_now_add=True)

    # just to show the name of this table cleaner in the management panel
    def __str__(self):
        return self.question[:50]