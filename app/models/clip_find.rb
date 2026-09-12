# frozen_string_literal: true

require "uri"

class ClipFind < ApplicationRecord
  PROHIBITED_CHARS_REGEX = /[;&|`$\n\r<>]/
  URL_REGEX = %r{\Ahttps?://[^\s;`$|&<>"]+\z}i

  validates :youtube_url, presence: true
  validates :youtube_url, format: { with: URL_REGEX, message: "is invalid or contains prohibited characters" }, allow_blank: true
  validates :model, length: { maximum: 48 }, allow_nil: true
  validate :validate_url_safety_and_host

  scope :recent, -> { order(created_at: :desc) }

  def self.latest_for(url)
    where(youtube_url: url).recent.first
  end

  private

  def validate_url_safety_and_host
    return if youtube_url.blank?

    if youtube_url.match?(PROHIBITED_CHARS_REGEX)
      errors.add(:youtube_url, "contains prohibited command characters")
      return
    end

    uri = URI.parse(youtube_url)
    unless uri.is_a?(URI::HTTP) && uri.host.present?
      errors.add(:youtube_url, "must have a valid HTTP or HTTPS host")
    end
  rescue URI::InvalidURIError
    errors.add(:youtube_url, "is an invalid URI")
  end
end
