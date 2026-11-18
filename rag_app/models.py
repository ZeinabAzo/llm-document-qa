import docx
from django.db import models

class Document(models.Model):
    file = models.FileField(upload_to='documents/')
    extracted_text = models.TextField(blank=True, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Save the file first so it exists on the filesystem
        super().save(*args, **kwargs)
        
        # Extract text only if a file exists and text hasn't been extracted yet
        if self.file and not self.extracted_text:
            try:
                # Open the uploaded word document
                doc = docx.Document(self.file.path)
                
                # Extract text from all paragraphs
                full_text = [para.text for para in doc.paragraphs]
                
                # Join paragraphs and store in the text field
                self.extracted_text = '\n'.join(full_text)
                
                # Save again to update the extracted_text field
                super().save(*args, **kwargs)
            except Exception as e:
                self.extracted_text = f"Error extracting text: {str(e)}"

    def __str__(self):
        return self.file.name


class QAHistory(models.Model):
    question = models.TextField()
    answer = models.TextField()
    asked_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.question[:50]