# Compatibility patch for JSON 3.0+ with Rails / ActiveSupport 8.1
# JSON 3.0 changed JSON.parse to use keyword arguments for options:
#   def parse(source, on_load: nil, object_class: nil, array_class: nil, **options)
# ActiveSupport 8.1 passes options as a positional hash:
#   ::JSON.parse(json, options)
# This patch enables JSON.parse to accept positional options hash.
module JSON
  class << self
    alias_method :_original_parse, :parse

    def parse(source, opts = nil, **kwargs)
      if opts.is_a?(Hash)
        _original_parse(source, **opts.merge(kwargs))
      elsif opts.nil?
        _original_parse(source, **kwargs)
      else
        _original_parse(source, opts, **kwargs)
      end
    end
  end
end
