Rails.application.routes.draw do
  get "up" => "rails/health#show", as: :rails_health_check

  root "dashboard#index"

  post "pipeline_runs/:id/approve", to: "dashboard#approve", as: :approve_pipeline_run
  post "telegram/webhook", to: "telegram_webhooks#create"
end
