require "cgi"
require "faraday"
require "json"

class TelegramBotService
  class Error < StandardError; end

  TELEGRAM_API_URL = "https://api.telegram.org"

  attr_reader :token, :default_chat_id

  def initialize(token: nil, default_chat_id: nil)
    @token = token.presence || ENV.fetch("TELEGRAM_BOT_TOKEN", nil) || ENV.fetch("OPENCLAW_TELEGRAM_BOT_TOKEN_FOR_REELBOT", nil)
    @default_chat_id = default_chat_id.presence || ENV.fetch("TELEGRAM_CHAT_ID", nil) || ENV.fetch("OPENCLAW_TELEGRAM_OWNER_ID_FOR_REELBOT", nil)
  end

  def notify(message, chat_id: nil, parse_mode: "HTML")
    target_chat = chat_id.presence || @default_chat_id
    raise ArgumentError, "chat_id is required to send Telegram message" if target_chat.blank?
    raise ArgumentError, "Telegram bot token is missing" if @token.blank?

    payload = {
      chat_id: target_chat,
      text: message,
      parse_mode: parse_mode
    }

    send_telegram_request("/sendMessage", payload)
  end

  def request_approval(pipeline_run, chat_id: nil)
    project = pipeline_run.video_project
    title = CGI.escapeHTML((project&.title || "Untitled Project").to_s)
    run_id = CGI.escapeHTML(pipeline_run.run_id.to_s)
    score = pipeline_run.quality_score || "N/A"
    video_path = CGI.escapeHTML((pipeline_run.final_video_path || pipeline_run.raw_video_path || "Pending").to_s)

    text = <<~MSG.strip
      🎬 <b>Approval Requested for Pipeline Run</b>

      <b>Project:</b> #{title}
      <b>Run ID:</b> <code>#{run_id}</code>
      <b>Quality Score:</b> #{score}/100
      <b>Video:</b> #{video_path}

      Please review and choose an action:
    MSG

    reply_markup = {
      inline_keyboard: [
        [
          { text: "✅ Approve", callback_data: "approve_#{run_id}" },
          { text: "❌ Reject", callback_data: "reject_#{run_id}" }
        ]
      ]
    }

    target_chat = chat_id.presence || @default_chat_id
    payload = {
      chat_id: target_chat,
      text: text,
      parse_mode: "HTML",
      reply_markup: reply_markup
    }

    send_telegram_request("/sendMessage", payload)
  end

  def connection
    @connection ||= Faraday.new(url: TELEGRAM_API_URL) do |builder|
      builder.adapter Faraday.default_adapter
    end
  end

  private

  def send_telegram_request(action, payload)
    response = connection.post("/bot#{@token}#{action}") do |req|
      req.headers["Content-Type"] = "application/json"
      req.body = JSON.dump(payload)
    end

    data = JSON.parse(response.body.to_s) rescue { "ok" => false, "error" => response.body }
    unless response.status == 200 && data["ok"]
      raise Error, "Telegram API error: #{data['description'] || response.body}"
    end

    data
  end
end
