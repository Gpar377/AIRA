#!/bin/bash

set -e

echo "🚀 Deploying NeuralOps Observability Stack"

# Add Helm repositories
echo "📦 Adding Helm repositories..."
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo add grafana https://grafana.github.io/helm-charts
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm repo update

# Create namespace
echo "📁 Creating observability namespace..."
kubectl create namespace observability --dry-run=client -o yaml | kubectl apply -f -

# Deploy Prometheus Stack (includes Grafana)
echo "📊 Deploying Prometheus + Grafana..."
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace observability \
  --values prometheus-values.yaml \
  --wait

# Deploy Loki
echo "📝 Deploying Loki..."
helm upgrade --install loki grafana/loki-stack \
  --namespace observability \
  --set loki.persistence.enabled=true \
  --set loki.persistence.size=5Gi \
  --set promtail.enabled=true \
  --wait

# Deploy Jaeger
echo "🔍 Deploying Jaeger..."
helm upgrade --install jaeger jaegertracing/jaeger \
  --namespace observability \
  --set provisionDataStore.cassandra=false \
  --set allInOne.enabled=true \
  --set storage.type=memory \
  --set agent.enabled=false \
  --set collector.enabled=false \
  --set query.enabled=false \
  --wait

echo "✅ Observability stack deployed successfully!"
echo ""
echo "📍 Access URLs (after port-forwarding):"
echo "   Prometheus: http://localhost:9090"
echo "   Grafana: http://localhost:3000 (admin/admin)"
echo "   Jaeger: http://localhost:16686"
echo ""
echo "🔌 Port forwarding commands:"
echo "   kubectl port-forward -n observability svc/prometheus-operated 9090:9090"
echo "   kubectl port-forward -n observability svc/prometheus-grafana 3000:80"
echo "   kubectl port-forward -n observability svc/jaeger-query 16686:16686"
echo "   kubectl port-forward -n observability svc/loki 3100:3100"
