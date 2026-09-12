# frozen_string_literal: true

class ChannelAccount < ApplicationRecord
  ACCOUNT_ROLES = %w[main clip creator brand competitor].freeze
  ACCOUNT_PLATFORMS = %w[youtube tiktok instagram].freeze
  SENSITIVE_CREDENTIAL_KEYS = %w[token access_token refresh_token cookies client_secret secret password].freeze

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
    unless options&.dig(:include_sensitive)
      if json["credentials"].is_a?(Hash)
        json["credentials"] = json["credentials"].reject do |key, _|
          SENSITIVE_CREDENTIAL_KEYS.include?(key.to_s.downcase) || key.to_s.downcase.match?(/token|cookie|secret|password/)
        end
      end
    end
    json
  end
end
