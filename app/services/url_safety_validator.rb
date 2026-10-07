# frozen_string_literal: true

require "uri"
require "ipaddr"
require "socket"
require "resolv"

class UrlSafetyValidator
  PROHIBITED_CHARS_REGEX = /[;&|`$\n\r<>]/

  RESERVED_NETWORKS = [
    IPAddr.new("0.0.0.0/8"),
    IPAddr.new("100.64.0.0/10"),
    IPAddr.new("192.0.0.0/24"),
    IPAddr.new("198.18.0.0/15"),
    IPAddr.new("240.0.0.0/4")
  ].freeze

  PRIVATE_HOST_SUFFIXES = %w[.localhost .local .internal .lan].freeze
  TRUSTED_DOMAINS = %w[youtube.com youtu.be].freeze

  class << self
    def validate!(url, trusted_only: false)
      raise ArgumentError, "URL cannot be blank" if url.blank?

      url_str = url.to_s.strip
      if url_str.match?(PROHIBITED_CHARS_REGEX)
        raise ArgumentError, "URL contains invalid or prohibited characters"
      end

      uri = URI.parse(url_str)
      unless uri.is_a?(URI::HTTP) && uri.host.present?
        raise ArgumentError, "URL must use HTTP or HTTPS scheme and have a host"
      end

      if trusted_only
        unless uri.scheme == "https"
          raise ArgumentError, "URL must use HTTPS scheme"
        end

        clean_host = uri.host.to_s.strip.downcase.delete_prefix("[").delete_suffix("]")
        unless trusted_domain?(clean_host)
          raise ArgumentError, "URL must belong to trusted domain (youtube.com, youtu.be)"
        end
      end

      if private_host?(uri.host)
        raise ArgumentError, "URL cannot target private or restricted network addresses"
      end

      uri
    rescue URI::InvalidURIError
      raise ArgumentError, "URL is invalid"
    end

    def validate_youtube_url!(url)
      validate!(url, trusted_only: true)
    end

    def private_host?(host)
      return true if host.blank?

      clean_host = host.to_s.strip.downcase.delete_prefix("[").delete_suffix("]")
      return true if clean_host == "localhost" || PRIVATE_HOST_SUFFIXES.any? { |suffix| clean_host.end_with?(suffix) }

      parsed_ip = parse_ip(clean_host)
      return true if parsed_ip && private_or_reserved_ip?(parsed_ip)

      unless trusted_domain?(clean_host)
        resolved_ips = resolve_host(clean_host)
        return true if resolved_ips.any? { |ip_str| (ip = parse_ip(ip_str)) && private_or_reserved_ip?(ip) }
      end

      false
    end

    def private_or_reserved_ip?(addr)
      return true if addr.loopback? || addr.private? || addr.link_local? || addr.to_i.zero?

      RESERVED_NETWORKS.any? { |net| net.include?(addr) }
    end

    private

    def parse_ip(str)
      addr = IPAddr.new(str)
      addr = addr.native if addr.respond_to?(:ipv4_mapped?) && addr.ipv4_mapped?
      addr
    rescue IPAddr::InvalidAddressError
      if str.match?(/\A(0x[0-9a-fA-F]+|\d+)\z/)
        int_val = begin
          Integer(str)
        rescue ArgumentError, TypeError
          nil
        end
        return IPAddr.new(int_val, Socket::AF_INET) if int_val && int_val >= 0 && int_val <= 0xffffffff
      end
      nil
    end

    def resolve_host(host)
      Resolv.getaddresses(host)
    rescue StandardError
      []
    end

    def trusted_domain?(host)
      TRUSTED_DOMAINS.any? do |domain|
        host == domain || host.end_with?(".#{domain}")
      end
    end
  end
end
