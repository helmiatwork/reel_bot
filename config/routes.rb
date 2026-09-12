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

  # Account endpoints
  resources :accounts, only: %i[index create update destroy] do
    member do
      post :cookies, to: "accounts#update_cookies"
      delete :cookies, to: "accounts#clear_cookies"
    end
  end

  # YouTube endpoints
  get "youtube/search", to: "you_tube#search"
  get "youtube/video/:id", to: "you_tube#video"
  get "youtube/channel/:id", to: "you_tube#channel"
  get "youtube/quota", to: "you_tube#quota"

  # Clip endpoints
  post "clips/transcript", to: "clips#transcript"
  post "clips/find-claude", to: "clips#find_claude"
  post "clips/auto", to: "clips#auto"
  post "clips/render", to: "clips#render_clip"
  get "clips/renders/:id/download", to: "clips#download_render", constraints: { id: %r{[^/]+} }
  get "dash/clip-finds", to: "clips#dash_clip_finds"
end
