require 'rails_helper'

RSpec.describe 'TelegramWebhooks', :regression, type: :request do
  let(:project) { create(:video_project) }
  let(:pipeline_run) { create(:pipeline_run, video_project: project, run_id: 'run-hook-001', status: :pending, quality_score: 88) }
  let(:telegram_service) { instance_double(TelegramBotService) }

  before do
    allow(TelegramBotService).to receive(:new).and_return(telegram_service)
    allow(telegram_service).to receive(:notify)
    allow(PublishVideoJob).to receive(:perform_later)
  end

  describe 'POST /telegram/webhook' do
    context 'with approve callback query' do
      let(:payload) do
        {
          update_id: 12345,
          callback_query: {
            id: 'cb_1',
            from: { id: 987654321 },
            message: {
              message_id: 42,
              chat: { id: 987654321 }
            },
            data: "approve_#{pipeline_run.run_id}"
          }
        }
      end

      it 'enqueues PublishVideoJob and sends confirmation' do
        expect(PublishVideoJob).to receive(:perform_later).with(pipeline_run.id)
        expect(telegram_service).to receive(:notify).with(
          include("Run #{pipeline_run.run_id} approved"),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: payload, as: :json

        expect(response).to have_http_status(:ok)
        pipeline_run.reload
        expect(pipeline_run.metadata['approval_status']).to eq('approved')
      end

      it 'notifies when run_id is not found' do
        unknown_payload = payload.deep_merge(callback_query: { data: 'approve_non-existent-run' })

        expect(PublishVideoJob).not_to receive(:perform_later)
        expect(telegram_service).to receive(:notify).with(
          include('non-existent-run not found'),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: unknown_payload, as: :json

        expect(response).to have_http_status(:ok)
      end
    end

    context 'with reject callback query' do
      let(:payload) do
        {
          update_id: 12346,
          callback_query: {
            id: 'cb_2',
            from: { id: 987654321 },
            message: {
              message_id: 42,
              chat: { id: 987654321 }
            },
            data: "reject_#{pipeline_run.run_id}"
          }
        }
      end

      it 'updates pipeline run status to failed and sends confirmation' do
        expect(PublishVideoJob).not_to receive(:perform_later)
        expect(telegram_service).to receive(:notify).with(
          include("Run #{pipeline_run.run_id} rejected"),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: payload, as: :json

        expect(response).to have_http_status(:ok)
        pipeline_run.reload
        expect(pipeline_run).to be_failed
        expect(pipeline_run.metadata['approval_status']).to eq('rejected')
      end

      it 'notifies when run_id is not found on reject' do
        unknown_payload = payload.deep_merge(callback_query: { data: 'reject_unknown-run' })

        expect(telegram_service).to receive(:notify).with(
          include('unknown-run not found'),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: unknown_payload, as: :json

        expect(response).to have_http_status(:ok)
      end
    end

    context 'with secret token verification' do
      let(:secret) { 'my-super-secret-token' }

      before do
        allow(ENV).to receive(:[]).and_call_original
        allow(ENV).to receive(:[]).with('TELEGRAM_WEBHOOK_SECRET').and_return(secret)
      end

      it 'allows request when secret token header matches' do
        post '/telegram/webhook',
             params: { message: { text: '/help', chat: { id: 123 } } },
             headers: { 'X-Telegram-Bot-Api-Secret-Token' => secret },
             as: :json

        expect(response).to have_http_status(:ok)
      end

      it 'returns 401 unauthorized when secret token header is missing' do
        post '/telegram/webhook',
             params: { message: { text: '/help', chat: { id: 123 } } },
             as: :json

        expect(response).to have_http_status(:unauthorized)
      end

      it 'returns 401 unauthorized when secret token header is invalid' do
        post '/telegram/webhook',
             params: { message: { text: '/help', chat: { id: 123 } } },
             headers: { 'X-Telegram-Bot-Api-Secret-Token' => 'wrong-token' },
             as: :json

        expect(response).to have_http_status(:unauthorized)
      end
    end

    context 'with /status command' do
      let(:payload) do
        {
          update_id: 12347,
          message: {
            message_id: 101,
            chat: { id: 987654321 },
            text: "/status #{pipeline_run.run_id}"
          }
        }
      end

      it 'replies with run status and quality score' do
        expect(telegram_service).to receive(:notify).with(
          include("Status for #{pipeline_run.run_id}", 'PENDING', '88'),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: payload, as: :json

        expect(response).to have_http_status(:ok)
      end

      it 'notifies when run is not found' do
        missing_payload = payload.deep_merge(message: { text: '/status nonexistent' })

        expect(telegram_service).to receive(:notify).with(
          include("nonexistent' not found"),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: missing_payload, as: :json

        expect(response).to have_http_status(:ok)
      end

      it 'replies with usage when run_id argument is omitted' do
        no_arg_payload = payload.deep_merge(message: { text: '/status' })

        expect(telegram_service).to receive(:notify).with(
          include('Usage:', '/status'),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: no_arg_payload, as: :json

        expect(response).to have_http_status(:ok)
      end
    end

    context 'with /help command' do
      let(:payload) do
        {
          update_id: 12348,
          message: {
            message_id: 102,
            chat: { id: 987654321 },
            text: '/help'
          }
        }
      end

      it 'replies with help text' do
        expect(telegram_service).to receive(:notify).with(
          include('ReelBot Commands', '/status', '/help'),
          chat_id: 987654321
        )

        post '/telegram/webhook', params: payload, as: :json

        expect(response).to have_http_status(:ok)
      end
    end

    context 'with unhandled message or empty payload' do
      it 'returns 200 OK without errors' do
        post '/telegram/webhook', params: { message: { text: 'hello world', chat: { id: 123 } } }, as: :json
        expect(response).to have_http_status(:ok)

        post '/telegram/webhook', params: {}, as: :json
        expect(response).to have_http_status(:ok)
      end
    end
  end
end
