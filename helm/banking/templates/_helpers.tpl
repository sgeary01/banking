{{/*
Expand the name of the chart.
*/}}
{{- define "banking.name" -}}
{{- .Chart.Name }}
{{- end }}

{{/*
Service URL helper — returns the in-cluster URL for a given service name.
Usage: {{ include "banking.serviceUrl" (dict "name" "auth-service" "port" 8001) }}
*/}}
{{- define "banking.serviceUrl" -}}
http://{{ .name }}:{{ .port }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "banking.labels" -}}
app.kubernetes.io/part-of: banking
app.kubernetes.io/managed-by: Helm
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
