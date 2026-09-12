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

    UrlSafetyValidator.validate!(youtube_url)
  rescue ArgumentError => e
    if e.message.include?("prohibited")
      errors.add(:youtube_url, "contains prohibited command characters")
    elsif e.message.include?("HTTP or HTTPS")
      errors.add(:youtube_url, "must have a valid HTTP or HTTPS host")
    elsif e.message.include?("private or restricted")
      errors.add(:youtube_url, "cannot target private or restricted network addresses")
    elsif e.message.include?("invalid")
      errors.add(:youtube_url, "is an invalid URI")
    else
      errors.add(:youtube_url, e.message)
    end
  end
end
