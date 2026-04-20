{{/*
Expand the name of the chart.
*/}}
{{- define "satellite.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name it will be used as a full name.
*/}}
{{- define "satellite.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "satellite.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "satellite.labels" -}}
helm.sh/chart: {{ include "satellite.chart" . }}
{{ include "satellite.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- range $key, $value := .Values.commonLabels }}
{{ $key }}: {{ $value | quote }}
{{- end }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "satellite.selectorLabels" -}}
app.kubernetes.io/name: {{ include "satellite.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Create the name of the service account to use
*/}}
{{- define "satellite.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "satellite.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}


{{/*
Function to convert k8s memory values to node heap values
*/}}
{{- define "convertK8sMemoryToNodeOption" -}}
{{- $memory := index . 0 -}}
{{- $heapFraction := index . 1 -}}
{{- $value := regexFind "([0-9]+)" $memory -}}
{{- $unit := regexFind "([EPTGMK][i]?)" $memory -}}
{{- if or (eq $value "") (eq $unit "") -}}
  {{- fail (print "Invalid memory format. " $memory " Must be a number followed by a unit (Ei, Pi, Ti, Gi, Mi, Ki, E, P, T, G, M, K). " $value $unit) -}}
{{- end -}}
{{- $value := int64 $value -}}

{{- $bytes := 0 -}}
{{- if eq $unit "Ei" -}}
  {{- $bytes = mul $value 1152921504606846976 -}}
{{- else if eq $unit "E" -}}
  {{- $bytes = mul $value 1000000000000000000 -}}
{{- else if eq $unit "Pi" -}}
  {{- $bytes = mul $value 1125899906842624 -}}
{{- else if eq $unit "P" -}}
  {{- $bytes = mul $value 1000000000000000 -}}
{{- else if eq $unit "Ti" -}}
  {{- $bytes = mul $value 1099511627776 -}}
{{- else if eq $unit "T" -}}
  {{- $bytes = mul $value 1000000000000 -}}
{{- else if eq $unit "Gi" -}}
  {{- $bytes = mul $value 1073741824 -}}
{{- else if eq $unit "G" -}}
  {{- $bytes = mul $value 1000000000 -}}
{{- else if eq $unit "Mi" -}}
  {{- $bytes = mul $value 1048576 -}}
{{- else if eq $unit "M" -}}
  {{- $bytes = mul $value 1000000 -}}
{{- else if eq $unit "Ki" -}}
  {{- $bytes = mul $value 1024 -}}
{{- else if eq $unit "K" -}}
  {{- $bytes = mul $value 1000 -}}
{{- end -}}

{{- $bytesForHeap := mulf $bytes (float64 $heapFraction) -}}

{{- $mbForHeap := div $bytesForHeap 1000000 -}}
{{- if lt $mbForHeap 1 -}}
  {{- fail (print "Invalid memory value " $memory ". limits.memory times heap.ratio must result in a value > 1mb") -}}
{{- end -}}

{{- printf "--max-old-space-size=%d" $mbForHeap -}}
{{- end -}}

{{/*
Check if git integration is enabled
*/}}
{{- define "satellite.hasGitIntegration" -}}
{{- $hasGit := false -}}
{{- range $key, $value := .Values.integrations -}}
  {{- if eq $value.type "git" -}}
    {{- $hasGit = true -}}
  {{- end -}}
{{- end -}}
{{- $hasGit -}}
{{- end -}}

{{- define "dnstap.port" -}}
{{- if .Values.dnstap }}
{{- .Values.dnstap.port | default 4444 }}
{{- else }}
{{- 4444 }}
{{- end }}
{{- end -}}

{{- define "validate.gitVolumeType" -}}
{{- if and (include "satellite.hasGitIntegration" . | eq "true") (ne .Values.gitVolume.type "emptyDir") (ne .Values.gitVolume.type "persistentVolumeClaim") -}}
  {{ fail (printf "Invalid `.Values.gitVolume.type`: %s" .Values.gitVolume.type) }}
{{- end -}}
{{- end -}}

{{/*
Common annotations
*/}}
{{- define "satellite.annotations" -}}
{{- range $key, $value := .Values.commonAnnotations }}
{{ $key }}: {{ $value | quote }}
{{- end }}
{{- end }}
