require 'rails_helper'

RSpec.describe ApplicationController, type: :controller do
  controller do
    def index
      render plain: 'ok'
    end
  end

  it 'inherits from ActionController::Base' do
    expect(described_class.superclass).to eq(ActionController::Base)
  end
end
