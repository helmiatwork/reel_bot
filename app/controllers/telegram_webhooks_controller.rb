class TelegramWebhooksController < ApplicationController
  protect_from_forgery with: :null_session
  skip_before_action :verify_authenticity_token, raise: false
  before_action :verify_secret_token

  def create
    if params[:callback_query].present?
      handle_callback_query(params[:callback_query])
    elsif params[:message].present?
      handle_message(params[:message])
    end

    head :ok
  end

  private

  def verify_secret_token
    secret = ENV["TELEGRAM_WEBHOOK_SECRET"]
    return if secret.blank?

    header_token = request.headers["X-Telegram-Bot-Api-Secret-Token"]
    if header_token.blank? || !ActiveSupport::SecurityUtils.secure_compare(header_token, secret)
      head :unauthorized
    end
  end

  def handle_callback_query(query)
    data = query[:data].to_s
    chat_id = query.dig(:message, :chat, :id) || query.dig(:from, :id)

    case data
    when /\Aapprove_(.+)\z/
      run_id = Regexp.last_match(1)
      pipeline_run = PipelineRun.find_by(run_id: run_id)

      if pipeline_run
        pipeline_run.update!(metadata: (pipeline_run.metadata || {}).merge("approval_status" => "approved"))
        PublishVideoJob.perform_later(pipeline_run.id)
        TelegramBotService.new.notify("✅ Run #{run_id} approved! Publishing enqueued.", chat_id: chat_id)
      else
        TelegramBotService.new.notify("❌ Run #{run_id} not found.", chat_id: chat_id)
      end
    when /\Areject_(.+)\z/
      run_id = Regexp.last_match(1)
      pipeline_run = PipelineRun.find_by(run_id: run_id)

      if pipeline_run
        pipeline_run.update!(status: :failed, metadata: (pipeline_run.metadata || {}).merge("approval_status" => "rejected"))
        TelegramBotService.new.notify("❌ Run #{run_id} rejected.", chat_id: chat_id)
      else
        TelegramBotService.new.notify("❌ Run #{run_id} not found.", chat_id: chat_id)
      end
    end
  end

  def handle_message(msg)
    text = msg[:text].to_s.strip
    chat_id = msg.dig(:chat, :id)
    return if chat_id.blank?

    case text
    when %r{\A/status(?:\s+(\S+))?\z}
      run_id = Regexp.last_match(1)
      if run_id.present?
        pipeline_run = PipelineRun.find_by(run_id: run_id)
        if pipeline_run
          status_msg = "📊 Status for #{run_id}: #{pipeline_run.status.upcase} (Score: #{pipeline_run.quality_score || 'N/A'})"
          TelegramBotService.new.notify(status_msg, chat_id: chat_id)
        else
          TelegramBotService.new.notify("❌ Pipeline run '#{run_id}' not found.", chat_id: chat_id)
        end
      else
        TelegramBotService.new.notify("Usage: <code>/status &lt;run_id&gt;</code>", chat_id: chat_id)
      end
    when %r{\A/help\b}
      help_text = <<~HELP.strip
        🤖 <b>ReelBot Commands</b>:
        • <code>/status &lt;run_id&gt;</code> - Check status of a pipeline run
        • <code>/help</code> - Show this help message
      HELP
      TelegramBotService.new.notify(help_text, chat_id: chat_id)
    end
  end
end
