# frozen_string_literal: true

class ChannelAccount < ApplicationRecord
  ACCOUNT_ROLES = %w[main clip creator brand competitor].freeze
  ACCOUNT_PLATFORMS = %w[youtube tiktok instagram].freeze
  SENSITIVE_CREDENTIAL_KEYS = %w[
    token access_token refresh_token cookies client_secret secret password api_key
  ].freeze

  alias_attribute :handle, :account_identifier
  alias_attribute :label, :account_name
  alias_attribute :active, :is_active

  has_many :analytics_snapshots, dependent: :destroy

  validates :platform, presence: true, inclusion: { in: ACCOUNT_PLATFORMS }
  validates :role, presence: true, inclusion: { in: ACCOUNT_ROLES }
  validates :account_name, presence: true
  validates :account_identifier, presence: true, uniqueness: { scope: :platform }
  validates :is_active, inclusion: { in: [ true, false ] }

  def cookies
    credentials&.dig("cookies")
  end

  def update_cookies(data)
    new_credentials = (credentials || {}).dup
    new_credentials["cookies"] = data
    update(credentials: new_credentials)
  end

  def clear_cookies!
    new_credentials = (credentials || {}).dup
    new_credentials.delete("cookies")
    update!(credentials: new_credentials)
  end

  def as_json(options = nil)
    json = super(options)
    include_sensitive = options.is_a?(Hash) && (options[:include_sensitive] || options["include_sensitive"])
    unless include_sensitive
      json["credentials"] = sanitize_credentials(json["credentials"]) if json["credentials"].present?
    end
    json
  end

  private

  def sanitize_credentials(obj)
    case obj
    when Hash
      obj.each_with_object({}) do |(key, value), acc|
        if sensitive_key?(key)
          acc[key] = "[FILTERED]"
        else
          acc[key] = sanitize_credentials(value)
        end
      end
    when Array
      obj.map { |item| sanitize_credentials(item) }
    else
      obj
    end
  end

  def sensitive_key?(key)
    key_str = key.to_s.downcase
    SENSITIVE_CREDENTIAL_KEYS.include?(key_str) || key_str.match?(/token|cookie|secret|password|api_key/)
  end
end
