require 'rails_helper'

RSpec.describe TelegramBotService do
  let(:token) { '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11' }
  let(:chat_id) { '987654321' }
  let(:service) { described_class.new(token: token, default_chat_id: chat_id) }

  describe '#notify' do
    it 'sends message via Telegram sendMessage endpoint' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/bot#{token}/sendMessage") do |env|
            body = JSON.parse(env.body)
            expect(body['chat_id']).to eq(chat_id)
            expect(body['text']).to eq('🚀 Processing started')
            expect(body['parse_mode']).to eq('HTML')
            [ 200, { 'content-type' => 'application/json' }, '{"ok": true, "result": {"message_id": 42}}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.notify('🚀 Processing started')
      expect(result['ok']).to be true
    end

    it 'allows custom chat_id override' do
      custom_chat = '555444333'
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/bot#{token}/sendMessage") do |env|
            body = JSON.parse(env.body)
            expect(body['chat_id']).to eq(custom_chat)
            [ 200, { 'content-type' => 'application/json' }, '{"ok": true}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.notify('Custom alert', chat_id: custom_chat)
      expect(result['ok']).to be true
    end
  end

  describe '#request_approval' do
    let(:project) { create(:video_project, title: 'AI in 2026') }
    let(:pipeline_run) do
      create(:pipeline_run,
             video_project: project,
             run_id: 'run-999',
             quality_score: 85,
             final_video_path: '/data/output/ai_2026.mp4')
    end

    it 'sends approval prompt with inline callback buttons' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/bot#{token}/sendMessage") do |env|
            body = JSON.parse(env.body)
            expect(body['chat_id']).to eq(chat_id)
            expect(body['text']).to include('AI in 2026')
            expect(body['text']).to include('run-999')
            expect(body['text']).to include('Quality Score')
            expect(body['text']).to include('85/100')

            buttons = body.dig('reply_markup', 'inline_keyboard', 0)
            expect(buttons).not_to be_nil
            approve_btn = buttons.find { |b| b['callback_data'] == 'approve_run-999' }
            reject_btn = buttons.find { |b| b['callback_data'] == 'reject_run-999' }

            expect(approve_btn['text']).to include('Approve')
            expect(reject_btn['text']).to include('Reject')

            [ 200, { 'content-type' => 'application/json' }, '{"ok": true}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.request_approval(pipeline_run)
      expect(result['ok']).to be true
    end

    it 'escapes special HTML characters in project title and run_id' do
      project.update!(title: '<Rock & Roll> Tips')
      pipeline_run.update!(run_id: 'run<123>&test')

      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/bot#{token}/sendMessage") do |env|
            body = JSON.parse(env.body)
            expect(body['text']).to include('&lt;Rock &amp; Roll&gt; Tips')
            expect(body['text']).to include('run&lt;123&gt;&amp;test')
            expect(body['text']).not_to include('<Rock & Roll>')
            [ 200, { 'content-type' => 'application/json' }, '{"ok": true}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      result = service.request_approval(pipeline_run)
      expect(result['ok']).to be true
    end
  end

  describe '#connection' do
    it 'creates a Faraday connection to Telegram API' do
      conn = service.connection
      expect(conn).to be_a(Faraday::Connection)
      expect(conn.url_prefix.to_s).to start_with('https://api.telegram.org')
    end
  end

  describe 'error handling' do
    it 'raises ArgumentError when chat_id is missing' do
      no_chat_service = described_class.new(token: token, default_chat_id: nil)
      expect {
        no_chat_service.notify('No chat')
      }.to raise_error(ArgumentError, /chat_id is required/)
    end

    it 'raises ArgumentError when token is missing' do
      no_token_service = described_class.new(token: nil, default_chat_id: chat_id)
      expect {
        no_token_service.notify('No token')
      }.to raise_error(ArgumentError, /Telegram bot token is missing/)
    end

    it 'raises TelegramBotService::Error when Telegram API returns failure' do
      stub_conn = Faraday.new do |builder|
        builder.adapter :test do |stub|
          stub.post("/bot#{token}/sendMessage") do |_env|
            [ 400, { 'content-type' => 'application/json' }, '{"ok": false, "description": "Chat not found"}' ]
          end
        end
      end

      allow(service).to receive(:connection).and_return(stub_conn)

      expect {
        service.notify('Fail test')
      }.to raise_error(TelegramBotService::Error, /Telegram API error: Chat not found/)
    end
  end
end
