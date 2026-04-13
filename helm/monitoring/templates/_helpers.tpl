{{- define "monitoring.labels" -}}
app.kubernetes.io/part-of: monitoring
app.kubernetes.io/managed-by: Helm
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end }}
