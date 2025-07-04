from django import forms


class CsvUploadForm(forms.Form):
    csv_file = forms.FileField(label="Upload CSV File")
