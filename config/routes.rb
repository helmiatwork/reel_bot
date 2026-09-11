Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check

  root "dashboard#index"

  post "pipeline_runs/:id/approve", to: "dashboard#approve", as: :approve_pipeline_run
  post "telegram/webhook", to: "telegram_webhooks#create"

  # Pipeline endpoints
  post "pipeline/run", to: "pipelines#create"
  get "pipeline/runs", to: "pipelines#index"
  get "pipeline/run/:id", to: "pipelines#show"

  # Voiceover endpoints
  post "voiceover/generate", to: "voiceovers#create"
  post "voiceover/merge", to: "voiceovers#merge"

  # Quality check endpoints
  post "quality/check", to: "quality_checks#create"

  # Publishing endpoints
  post "publish", to: "publishings#create"

  # Analytics endpoints
  get "analytics/data", to: "analytics#data"
  get "analytics/summary", to: "analytics#summary"
  get "analytics/insights", to: "analytics#insights"
end
