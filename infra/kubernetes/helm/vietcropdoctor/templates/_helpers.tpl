{{/*
Expand the name of the chart.
*/}}
{{- define "vietcropdoctor.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name using chart + release.
*/}}
{{- define "vietcropdoctor.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Chart label: name + version.
*/}}
{{- define "vietcropdoctor.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
Usage: include "vietcropdoctor.labels" (dict "svcName" $name "root" $)
*/}}
{{- define "vietcropdoctor.labels" -}}
helm.sh/chart: {{ include "vietcropdoctor.chart" .root }}
app.kubernetes.io/name: {{ .svcName }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/version: {{ .root.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .root.Release.Service }}
{{- end }}

{{/*
Selector labels (subset of common labels, must be immutable after first deploy).
Usage: include "vietcropdoctor.selectorLabels" (dict "svcName" $name "root" $)
*/}}
{{- define "vietcropdoctor.selectorLabels" -}}
app.kubernetes.io/name: {{ .svcName }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
{{- end }}

{{/*
Image reference: registry/image:tag, falling back to global values.
Usage: include "vietcropdoctor.image" (dict "svc" $svc "root" $)
*/}}
{{- define "vietcropdoctor.image" -}}
{{- $reg := .root.Values.global.registry -}}
{{- $tag := .root.Values.global.imageTag -}}
{{- printf "%s/%s:%s" $reg .svc.image $tag }}
{{- end }}

{{/*
Namespace — always from global.namespace.
*/}}
{{- define "vietcropdoctor.namespace" -}}
{{- .Values.global.namespace }}
{{- end }}
